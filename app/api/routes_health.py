from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "macrochef-agent"}


@router.get("/")
def root() -> dict[str, str]:
    return {
        "service": "macrochef-agent",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }
