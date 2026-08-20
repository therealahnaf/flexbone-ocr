from collections.abc import Sequence
from typing import Protocol

from app.domain.models import (
    BatchOcrResult,
    CachedOcrResult,
    InspectedImage,
    OcrProviderResult,
    OcrResult,
    RateLimitDecision,
    ValidatedImage,
)


class UploadSource(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


class OcrProvider(Protocol):
    async def extract_text(self, content: bytes) -> OcrProviderResult: ...


class OcrCache(Protocol):
    async def get(self, key: str) -> CachedOcrResult | None: ...

    async def set(self, key: str, value: CachedOcrResult) -> None: ...


class ImageValidator(Protocol):
    async def validate(self, upload: UploadSource) -> ValidatedImage: ...


class ImageInspector(Protocol):
    def inspect(self, content: bytes) -> InspectedImage: ...


class TextProcessor(Protocol):
    def clean(self, text: str) -> str: ...


class OcrUseCase(Protocol):
    async def extract(self, upload: UploadSource) -> OcrResult: ...


class BatchOcrUseCase(Protocol):
    async def extract(
        self,
        uploads: Sequence[UploadSource],
        request_id: str,
    ) -> BatchOcrResult: ...


class RateLimiter(Protocol):
    async def check(self, client_id: str) -> RateLimitDecision: ...
