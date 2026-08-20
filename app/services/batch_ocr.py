import asyncio
import logging
import time
from collections.abc import Sequence

from app.core.errors import AppError
from app.domain.models import BatchOcrResult, ErrorDetail, OcrItemFailure, OcrResult
from app.domain.ports import OcrUseCase, UploadSource

logger = logging.getLogger(__name__)


class BatchOcrService:
    def __init__(self, ocr_service: OcrUseCase, max_files: int):
        self._ocr_service = ocr_service
        self._max_files = max_files

    async def extract(
        self,
        uploads: Sequence[UploadSource],
        request_id: str,
    ) -> BatchOcrResult:
        self._validate_batch_size(uploads)
        started = time.perf_counter()
        results = tuple(
            await asyncio.gather(*(self._extract_one(upload, request_id) for upload in uploads))
        )
        successful = sum(isinstance(result, OcrResult) for result in results)
        failed = len(results) - successful
        return BatchOcrResult(
            success=failed == 0,
            total=len(results),
            successful=successful,
            failed=failed,
            processing_time_ms=max(
                0,
                round((time.perf_counter() - started) * 1000),
            ),
            results=results,
        )

    def _validate_batch_size(self, uploads: Sequence[UploadSource]) -> None:
        if not uploads:
            raise AppError(422, "missing_images", "At least one image is required.")
        if len(uploads) > self._max_files:
            raise AppError(
                422,
                "too_many_images",
                f"A batch can contain at most {self._max_files} images.",
            )

    async def _extract_one(
        self,
        upload: UploadSource,
        request_id: str,
    ) -> OcrResult | OcrItemFailure:
        try:
            return await self._ocr_service.extract(upload)
        except AppError as error:
            return OcrItemFailure(
                filename=upload.filename or "unnamed",
                error=ErrorDetail(code=error.code, message=error.message),
                request_id=request_id,
            )
        except Exception:
            logger.exception(
                "Unexpected batch item failure",
                extra={"request_id": request_id},
            )
            return OcrItemFailure(
                filename=upload.filename or "unnamed",
                error=ErrorDetail(
                    code="internal_error",
                    message="An unexpected error occurred.",
                ),
                request_id=request_id,
            )
