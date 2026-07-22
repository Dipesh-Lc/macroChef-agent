from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_day_planner import router as day_planner_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_health import router as health_router
from app.api.routes_inventory import router as inventory_router
from app.api.routes_library import router as library_router
from app.api.routes_recommendations import router as recommendations_router
from app.api.routes_safety_tools import router as safety_tools_router
from app.api.routes_session import router as session_router
from app.api.routes_share import router as share_router
from app.data.db import init_db
from app.dependencies import validate_session_secret_at_startup
from app.spa import mount_spa


def create_app() -> FastAPI:
    app = FastAPI(
        title="MacroChef Agent",
        description="A multimodal, constraint-aware meal planning system.",
        version="0.1.0",
    )
    # SPA rebuild W6 cutover: the React SPA is now served BY this same
    # FastAPI process, same-origin, in every environment except local Vite
    # dev (app/spa.py's mount_spa; the built `web/dist` is baked into the
    # deploy image). A same-origin browser request is never subject to CORS
    # at all, so `MACROCHEF_FRONTEND_ORIGIN` (a separate Streamlit-origin
    # setting) no longer means anything and has been removed -- see
    # .env.example's git history for the prior Streamlit-era value.
    # The one case this middleware still matters for is local dev against
    # the Vite dev server (`web/vite.config.ts`, default
    # http://localhost:5173) -- even though Vite's own dev proxy makes
    # ordinary API calls same-origin from the browser's point of view, this
    # stays here as defense in depth / for direct browser exploration of
    # this port's /docs. `allow_origins=["*"]` combined with
    # `allow_credentials=True` is both rejected by browsers and wrong once
    # cookies exist, so this lists concrete localhost origins instead of a
    # wildcard.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        # `allow_credentials=False` is LOAD-BEARING for the cookie-CSRF model
        # introduced by POST /session (app/api/routes_session.py) and the
        # `mc_session` cookie dual-read in
        # app.dependencies.get_session_user: a cross-origin browser request
        # cannot attach a custom header (X-Session-Token, or
        # X-Requested-With alongside the cookie) to a *credentialed*
        # (cookie-carrying) cross-site request unless this server's CORS
        # policy opts that origin into `allow_credentials=True` -- and even
        # then, browsers refuse to send cookies cross-site at all unless
        # this middleware echoes the specific requesting origin (never `*`)
        # AND sets allow_credentials=True. Flipping this to True without
        # redesigning the CSRF story first would let any allowed origin's
        # page issue cookie-authenticated requests cross-site. See
        # tests/test_session_endpoint.py for the regression test asserting
        # this stays False.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(inventory_router)
    app.include_router(recommendations_router)
    app.include_router(library_router)
    app.include_router(feedback_router)
    app.include_router(day_planner_router)
    app.include_router(safety_tools_router)
    app.include_router(share_router)
    app.include_router(session_router)

    @app.on_event("startup")
    def _startup() -> None:
        # Fail closed BEFORE the app can serve traffic if SESSION_SECRET is
        # missing outside local dev -- see app.dependencies for the signal
        # used to detect local dev and why raising here (not warning) matters.
        validate_session_secret_at_startup()
        init_db()

    # LAST: mounts the built SPA (if present) + its catch-all client-routing
    # fallback. Must stay after every app.include_router(...) call above --
    # see app/spa.py's module docstring for why ordering matters here.
    mount_spa(app)

    return app


app = create_app()
