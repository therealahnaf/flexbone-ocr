from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.container import ApplicationContainer
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.domain.ports import OcrProvider


def create_app(
    settings: Settings | None = None,
    provider: OcrProvider | None = None,
) -> FastAPI:
    configure_logging()
    container = ApplicationContainer.build(settings or get_settings(), provider)

    application = FastAPI(
        title="Flexbone API",
        version="0.1.0",
        description="Secure image OCR API powered by Google Cloud Vision.",
    )
    application.state.container = container
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()
