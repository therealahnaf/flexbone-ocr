from dataclasses import dataclass, field
from typing import Literal

ImageFormat = Literal["JPEG", "PNG", "GIF"]


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    filename: str
    format: ImageFormat
    content_type: str
    size_bytes: int
    width: int
    height: int
    mode: str
    frame_count: int = 1


@dataclass(frozen=True, slots=True)
class InspectedImage:
    format: ImageFormat
    width: int
    height: int
    mode: str
    frame_count: int = 1


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    content: bytes
    digest: str
    metadata: ImageMetadata


@dataclass(frozen=True, slots=True)
class OcrProviderResult:
    text: str
    confidences: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class CachedOcrResult:
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    confidence: float
    processing_time_ms: int
    cached: bool
    metadata: ImageMetadata
    success: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class OcrItemFailure:
    filename: str
    error: ErrorDetail
    request_id: str
    success: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class BatchOcrResult:
    total: int
    successful: int
    failed: int
    processing_time_ms: int
    results: tuple[OcrResult | OcrItemFailure, ...]
    success: bool


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0
