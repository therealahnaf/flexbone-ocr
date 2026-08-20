from typing import Annotated

from fastapi import Depends, Request

from app.core.container import ApplicationContainer
from app.core.errors import RateLimitError
from app.domain.ports import BatchOcrUseCase, OcrUseCase


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_ocr_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> OcrUseCase:
    return container.ocr_service


def get_batch_ocr_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> BatchOcrUseCase:
    return container.batch_ocr_service


async def enforce_rate_limit(
    request: Request,
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> None:
    client_id = request.client.host if request.client else "unknown"
    decision = await container.rate_limiter.check(client_id)
    if not decision.allowed:
        raise RateLimitError(decision.retry_after)
