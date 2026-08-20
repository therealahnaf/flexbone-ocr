from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.api.dependencies import (
    enforce_rate_limit,
    get_batch_ocr_service,
    get_ocr_service,
)
from app.domain.models import BatchOcrResult, OcrResult
from app.domain.ports import BatchOcrUseCase, OcrUseCase
from app.schemas.errors import ErrorResponse
from app.schemas.ocr import BatchResponse, OcrResponse

router = APIRouter(tags=["ocr"])

error_responses = {
    413: {"model": ErrorResponse, "description": "Image exceeds a configured limit."},
    415: {"model": ErrorResponse, "description": "Image format is unsupported or mismatched."},
    422: {"model": ErrorResponse, "description": "Request or image is invalid."},
    429: {"model": ErrorResponse, "description": "Per-client request limit exceeded."},
    502: {"model": ErrorResponse, "description": "Google Vision could not process the image."},
}


@router.post(
    "/extract-text",
    response_model=OcrResponse,
    responses=error_responses,
    dependencies=[Depends(enforce_rate_limit)],
)
async def extract_text(
    image: Annotated[UploadFile, File(description="A JPG, JPEG, PNG, or GIF image.")],
    service: Annotated[OcrUseCase, Depends(get_ocr_service)],
) -> OcrResult:
    return await service.extract(image)


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
    service: Annotated[BatchOcrUseCase, Depends(get_batch_ocr_service)],
) -> BatchOcrResult:
    return await service.extract(images, request.state.request_id)
