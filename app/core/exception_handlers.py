import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError
from app.schemas.errors import ErrorDetailSchema, ErrorResponse

logger = logging.getLogger(__name__)


def error_response(request: Request, error: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    body = ErrorResponse(
        error=ErrorDetailSchema(code=error.code, message=error.message),
        request_id=request_id,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(),
        headers=error.headers,
    )


def register_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        return error_response(request, error)

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            request,
            AppError(422, "invalid_request", "The multipart request is invalid."),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _error: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled application error",
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return error_response(
            request,
            AppError(500, "internal_error", "An unexpected error occurred."),
        )
