from dataclasses import dataclass

from app.core.config import Settings
from app.domain.ports import BatchOcrUseCase, OcrProvider, OcrUseCase, RateLimiter
from app.infra.cache import InMemoryOcrCache
from app.infra.google_vision import GoogleVisionOcrProvider
from app.infra.image_inspection import PillowImageInspector
from app.infra.rate_limit import InMemoryRateLimiter
from app.services.batch_ocr import BatchOcrService
from app.services.image_validation import ImageValidationService
from app.services.ocr import OcrService
from app.services.text_processing import TextProcessingService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: Settings
    ocr_service: OcrUseCase
    batch_ocr_service: BatchOcrUseCase
    rate_limiter: RateLimiter

    @classmethod
    def build(
        cls,
        settings: Settings,
        provider: OcrProvider | None = None,
    ) -> "ApplicationContainer":
        ocr_service = OcrService(
            provider=provider or GoogleVisionOcrProvider(settings.vision_timeout_seconds),
            validator=ImageValidationService(
                settings.max_file_size_bytes,
                settings.max_image_pixels,
                PillowImageInspector(),
            ),
            text_processor=TextProcessingService(),
            cache=InMemoryOcrCache(
                settings.cache_max_entries,
                settings.cache_ttl_seconds,
            ),
            concurrency=settings.batch_concurrency,
        )
        return cls(
            settings=settings,
            ocr_service=ocr_service,
            batch_ocr_service=BatchOcrService(ocr_service, settings.batch_max_files),
            rate_limiter=InMemoryRateLimiter(
                settings.rate_limit_requests,
                settings.rate_limit_window_seconds,
            ),
        )
