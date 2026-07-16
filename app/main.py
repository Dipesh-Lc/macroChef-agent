import os

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
    # `allow_origins=["*"]` combined with `allow_credentials=True` is both
    # rejected by browsers and wrong once cookies exist: it would tell any
    # origin's browser JS it may make credentialed requests here. In this
    # deployment topology the browser only ever talks to Streamlit (the sole
    # public surface); this FastAPI process stays on localhost and is called
    # server-to-server by Streamlit's Python process, which isn't subject to
    # CORS at all -- so this mostly matters for local browser-based API
    # exploration (e.g. /docs) and defense in depth, not as the isolation
    # boundary (that's app.dependencies.get_session_user). No browser
    # ever needs to send FastAPI a cookie directly (the session cookie lives
    # on Streamlit's origin), so credentials stay disabled.
    _frontend_origin = os.getenv("MACROCHEF_FRONTEND_ORIGIN", "http://localhost:8501")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_frontend_origin, "http://localhost:8000"],
        allow_credentials=False,
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
