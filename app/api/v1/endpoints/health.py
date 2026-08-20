from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "Flexbone API"}


@router.get("/api/v1/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
