from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_feedback import router as feedback_router
from app.api.routes_health import router as health_router
from app.api.routes_inventory import router as inventory_router
from app.api.routes_library import router as library_router
from app.api.routes_recommendations import router as recommendations_router
from app.data.db import init_db


def create_app() -> FastAPI:
    app = FastAPI(
        title="MacroChef Agent",
        description="A multimodal, constraint-aware meal planning system.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(inventory_router)
    app.include_router(recommendations_router)
    app.include_router(library_router)
    app.include_router(feedback_router)

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    return app


app = create_app()
