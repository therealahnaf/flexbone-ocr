from fastapi import FastAPI

from app.routers import health


def create_app() -> FastAPI:
    application = FastAPI(
        title="Flexbone API",
        version="0.1.0",
    )
    application.include_router(health.router, prefix="/api/v1")

    @application.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {"message": "Flexbone API"}

    return application


app = create_app()
