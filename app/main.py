import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import AppError
from app.models import ErrorDetail, ErrorResponse
from app.rate_limit import InMemoryRateLimiter
from app.routers import health, ocr
from app.services import (
    GoogleVisionOcrProvider,
    ImageValidator,
    InMemoryOcrCache,
    OcrProvider,
    OcrService,
    TextProcessor,
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if not any(getattr(handler, "_flexbone_json", False) for handler in root_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._flexbone_json = True  # type: ignore[attr-defined]
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def _error_response(request: Request, error: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    body = ErrorResponse(
        error=ErrorDetail(code=error.code, message=error.message),
        request_id=request_id,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(),
        headers=error.headers,
    )


def create_app(
    settings: Settings | None = None,
    provider: OcrProvider | None = None,
) -> FastAPI:
    configure_logging()
    application_settings = settings or get_settings()
    ocr_provider = provider or GoogleVisionOcrProvider(
        application_settings.vision_timeout_seconds
    )

    application = FastAPI(
        title="Flexbone API",
        version="0.1.0",
        description="Secure image OCR API powered by Google Cloud Vision.",
    )
    application.state.settings = application_settings
    application.state.ocr_service = OcrService(
        provider=ocr_provider,
        validator=ImageValidator(
            application_settings.max_file_size_bytes,
            application_settings.max_image_pixels,
        ),
        text_processor=TextProcessor(),
        cache=InMemoryOcrCache(
            application_settings.cache_max_entries,
            application_settings.cache_ttl_seconds,
        ),
        concurrency=application_settings.batch_concurrency,
    )
    application.state.rate_limiter = InMemoryRateLimiter(
        application_settings.rate_limit_requests,
        application_settings.rate_limit_window_seconds,
    )

    application.include_router(health.router, prefix="/api/v1")
    application.include_router(ocr.router)

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("flexbone.request").info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        return _error_response(request, error)

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            AppError(422, "invalid_request", "The multipart request is invalid."),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _error: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception(
            "Unhandled application error",
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return _error_response(
            request,
            AppError(500, "internal_error", "An unexpected error occurred."),
        )

    @application.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {"message": "Flexbone API"}

    return application


app = create_app()
