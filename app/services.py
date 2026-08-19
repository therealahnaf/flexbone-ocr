import asyncio
import hashlib
import io
import logging
import threading
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Protocol

import anyio
from cachetools import TTLCache
from fastapi import UploadFile
from google.cloud import vision
from PIL import Image, UnidentifiedImageError

from app.errors import (
    FileTooLargeError,
    InvalidImageError,
    OcrProviderError,
    UnsupportedImageError,
)
from app.models import ImageMetadata, OcrResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    text: str
    confidences: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class CachedOcrResult:
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    content: bytes
    digest: str
    metadata: ImageMetadata


class OcrProvider(Protocol):
    async def extract_text(self, content: bytes) -> ProviderResult: ...


class OcrCache(Protocol):
    async def get(self, key: str) -> CachedOcrResult | None: ...

    async def set(self, key: str, value: CachedOcrResult) -> None: ...


class InMemoryOcrCache:
    def __init__(self, max_entries: int, ttl_seconds: int):
        self._cache: TTLCache[str, CachedOcrResult] = TTLCache(
            maxsize=max_entries,
            ttl=ttl_seconds,
        )
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> CachedOcrResult | None:
        async with self._lock:
            return self._cache.get(key)

    async def set(self, key: str, value: CachedOcrResult) -> None:
        async with self._lock:
            self._cache[key] = value


class ImageValidator:
    _extensions = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".gif": "GIF",
    }
    _content_types = {
        "image/jpeg": "JPEG",
        "image/jpg": "JPEG",
        "image/png": "PNG",
        "image/gif": "GIF",
    }

    def __init__(self, max_file_size_bytes: int, max_image_pixels: int):
        self._max_file_size = max_file_size_bytes
        self._max_image_pixels = max_image_pixels

    async def validate(self, upload: UploadFile) -> ValidatedImage:
        filename = upload.filename or ""
        extension_format = self._extensions.get(Path(filename).suffix.lower())
        content_type = (upload.content_type or "").lower()
        content_type_format = self._content_types.get(content_type)

        if not extension_format or not content_type_format:
            raise UnsupportedImageError()
        if extension_format != content_type_format:
            raise UnsupportedImageError(
                "The filename extension and Content-Type do not describe the same image format."
            )

        content = await upload.read(self._max_file_size + 1)
        if not content:
            raise InvalidImageError("The uploaded image is empty.")
        if len(content) > self._max_file_size:
            raise FileTooLargeError(
                f"Each image must be at most {self._max_file_size} bytes."
            )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as opened_image:
                    actual_format = opened_image.format
                    width, height = opened_image.size
                    mode = opened_image.mode
                    frame_count = getattr(opened_image, "n_frames", 1)

                    if width * height > self._max_image_pixels:
                        raise FileTooLargeError(
                            f"Image dimensions must not exceed {self._max_image_pixels} pixels."
                        )
                    if actual_format != extension_format:
                        raise UnsupportedImageError(
                            "The image contents do not match its filename and Content-Type."
                        )

                    opened_image.verify()
        except (FileTooLargeError, UnsupportedImageError):
            raise
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombWarning) as exc:
            raise InvalidImageError() from exc

        metadata = ImageMetadata(
            filename=filename,
            format=actual_format,
            content_type=content_type,
            size_bytes=len(content),
            width=width,
            height=height,
            mode=mode,
            frame_count=frame_count,
        )
        return ValidatedImage(
            content=content,
            digest=hashlib.sha256(content).hexdigest(),
            metadata=metadata,
        )


class TextProcessor:
    @staticmethod
    def clean(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in normalized.split("\n")]

        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()

        cleaned: list[str] = []
        blank_count = 0
        for line in lines:
            if line:
                blank_count = 0
                cleaned.append(line)
                continue
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")

        return "\n".join(cleaned)


class GoogleVisionOcrProvider:
    """Google-specific adapter. The client is created lazily for testability."""

    def __init__(self, timeout_seconds: float, client: Any | None = None):
        self._timeout = timeout_seconds
        self._client = client
        self._client_lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = vision.ImageAnnotatorClient()
        return self._client

    async def extract_text(self, content: bytes) -> ProviderResult:
        def call_vision() -> Any:
            image = vision.Image(content=content)
            return self._get_client().document_text_detection(
                image=image,
                timeout=self._timeout,
            )

        try:
            response = await anyio.to_thread.run_sync(call_vision)
        except Exception as exc:
            raise OcrProviderError() from exc

        if response.error.message:
            logger.warning("Google Vision returned an OCR error: %s", response.error.message)
            raise OcrProviderError()

        full_text = getattr(response.full_text_annotation, "text", "") or ""
        if not full_text and response.text_annotations:
            full_text = response.text_annotations[0].description or ""

        confidences: list[float] = []
        for page in getattr(response.full_text_annotation, "pages", ()):
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        confidence = float(getattr(word, "confidence", 0.0))
                        if 0.0 < confidence <= 1.0:
                            confidences.append(confidence)

        return ProviderResult(full_text, tuple(confidences))


class OcrService:
    def __init__(
        self,
        provider: OcrProvider,
        validator: ImageValidator,
        text_processor: TextProcessor,
        cache: OcrCache,
        concurrency: int,
    ):
        self._provider = provider
        self._validator = validator
        self._text_processor = text_processor
        self._cache = cache
        self._provider_slots = asyncio.Semaphore(concurrency)
        self._inflight: dict[str, asyncio.Task[CachedOcrResult]] = {}
        self._inflight_lock = asyncio.Lock()

    async def process(self, upload: UploadFile) -> OcrResponse:
        started = time.perf_counter()
        image = await self._validator.validate(upload)
        cached_result = await self._cache.get(image.digest)

        if cached_result is not None:
            return OcrResponse(
                text=cached_result.text,
                confidence=cached_result.confidence,
                processing_time_ms=self._elapsed_ms(started),
                cached=True,
                metadata=image.metadata,
            )

        async with self._inflight_lock:
            inflight = self._inflight.get(image.digest)
            created = inflight is None
            if inflight is None:
                inflight = asyncio.create_task(
                    self._extract_and_cache(image.digest, image.content)
                )
                self._inflight[image.digest] = inflight

        try:
            result = await inflight
        finally:
            if created:
                async with self._inflight_lock:
                    if self._inflight.get(image.digest) is inflight:
                        self._inflight.pop(image.digest, None)

        return OcrResponse(
            text=result.text,
            confidence=result.confidence,
            processing_time_ms=self._elapsed_ms(started),
            cached=not created,
            metadata=image.metadata,
        )

    async def _extract_and_cache(self, digest: str, content: bytes) -> CachedOcrResult:
        async with self._provider_slots:
            provider_result = await self._provider.extract_text(content)

        result = CachedOcrResult(
            text=self._text_processor.clean(provider_result.text),
            confidence=self._average_confidence(provider_result.confidences),
        )
        await self._cache.set(digest, result)
        return result

    @staticmethod
    def _average_confidence(confidences: tuple[float, ...]) -> float:
        valid = [value for value in confidences if 0.0 < value <= 1.0]
        return round(fmean(valid), 4) if valid else 0.0

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))
