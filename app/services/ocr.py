import asyncio
import time
from statistics import fmean

from app.domain.models import CachedOcrResult, OcrResult
from app.domain.ports import (
    ImageValidator,
    OcrCache,
    OcrProvider,
    TextProcessor,
    UploadSource,
)


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

    async def extract(self, upload: UploadSource) -> OcrResult:
        started = time.perf_counter()
        image = await self._validator.validate(upload)
        cached_result = await self._cache.get(image.digest)

        if cached_result is not None:
            return OcrResult(
                text=cached_result.text,
                confidence=cached_result.confidence,
                processing_time_ms=self._elapsed_ms(started),
                cached=True,
                metadata=image.metadata,
            )

        result, shared = await self._extract_once(image.digest, image.content)
        return OcrResult(
            text=result.text,
            confidence=result.confidence,
            processing_time_ms=self._elapsed_ms(started),
            cached=shared,
            metadata=image.metadata,
        )

    async def _extract_once(
        self,
        digest: str,
        content: bytes,
    ) -> tuple[CachedOcrResult, bool]:
        async with self._inflight_lock:
            inflight = self._inflight.get(digest)
            created = inflight is None
            if inflight is None:
                inflight = asyncio.create_task(self._extract_and_cache(digest, content))
                self._inflight[digest] = inflight

        try:
            return await inflight, not created
        finally:
            if created:
                async with self._inflight_lock:
                    if self._inflight.get(digest) is inflight:
                        self._inflight.pop(digest, None)

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
