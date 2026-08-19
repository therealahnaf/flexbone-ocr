import asyncio
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.errors import AppError, RateLimitError
from app.models import BatchItemError, BatchResponse, ErrorDetail, ErrorResponse, OcrResponse
from app.services import OcrService

router = APIRouter(tags=["ocr"])
logger = logging.getLogger(__name__)

error_responses = {
    413: {"model": ErrorResponse, "description": "Image exceeds a configured limit."},
    415: {"model": ErrorResponse, "description": "Image format is unsupported or mismatched."},
    422: {"model": ErrorResponse, "description": "Request or image is invalid."},
    429: {"model": ErrorResponse, "description": "Per-client request limit exceeded."},
    502: {"model": ErrorResponse, "description": "Google Vision could not process the image."},
}


def get_ocr_service(request: Request) -> OcrService:
    return request.app.state.ocr_service


async def enforce_rate_limit(request: Request) -> None:
    client_id = request.client.host if request.client else "unknown"
    decision = await request.app.state.rate_limiter.check(client_id)
    if not decision.allowed:
        raise RateLimitError(decision.retry_after)


@router.post(
    "/extract-text",
    response_model=OcrResponse,
    responses=error_responses,
    dependencies=[Depends(enforce_rate_limit)],
)
async def extract_text(
    image: Annotated[UploadFile, File(description="A JPG, JPEG, PNG, or GIF image.")],
    service: Annotated[OcrService, Depends(get_ocr_service)],
) -> OcrResponse:
    return await service.process(image)


@router.post(
    "/extract-text/batch",
    response_model=BatchResponse,
    responses=error_responses,
    dependencies=[Depends(enforce_rate_limit)],
)
async def extract_text_batch(
    request: Request,
    images: Annotated[
        list[UploadFile],
        File(description="One to five JPG, JPEG, PNG, or GIF images."),
    ],
    service: Annotated[OcrService, Depends(get_ocr_service)],
) -> BatchResponse:
    settings = request.app.state.settings
    if not images:
        raise AppError(422, "missing_images", "At least one image is required.")
    if len(images) > settings.batch_max_files:
        raise AppError(
            422,
            "too_many_images",
            f"A batch can contain at most {settings.batch_max_files} images.",
        )

    request_id = request.state.request_id
    started = time.perf_counter()

    async def process_one(upload: UploadFile) -> OcrResponse | BatchItemError:
        try:
            return await service.process(upload)
        except AppError as exc:
            return BatchItemError(
                filename=upload.filename or "unnamed",
                error=ErrorDetail(code=exc.code, message=exc.message),
                request_id=request_id,
            )
        except Exception:
            logger.exception(
                "Unexpected batch item failure",
                extra={"request_id": request_id},
            )
            return BatchItemError(
                filename=upload.filename or "unnamed",
                error=ErrorDetail(
                    code="internal_error",
                    message="An unexpected error occurred.",
                ),
                request_id=request_id,
            )

    results = list(await asyncio.gather(*(process_one(upload) for upload in images)))
    successful = sum(isinstance(result, OcrResponse) for result in results)
    failed = len(results) - successful
    elapsed = max(0, round((time.perf_counter() - started) * 1000))
    return BatchResponse(
        success=failed == 0,
        total=len(results),
        successful=successful,
        failed=failed,
        processing_time_ms=elapsed,
        results=results,
    )
