from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_admin import router as admin_router
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
from app.observability.events import new_run_id, reset_run_id, set_run_id
from app.observability.tracing import init_tracing, shutdown_tracing
from app.spa import mount_spa

# Header a request can supply to propagate its own correlation id (e.g. an
# upstream gateway/load balancer already minted one); otherwise a fresh id
# is minted per request. Read by the request-id middleware below and echoed
# back on the response so a caller can correlate its request with server
# logs/RunEvents (app.observability.events) without needing to grep by
# timestamp -- ROADMAP.md Phase 1, Step 1.1.
REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware:
    """Plain ASGI middleware (deliberately NOT `BaseHTTPMiddleware`): it
    calls the wrapped app directly in the current asyncio Task rather than
    spawning a new one, so the `run_id` contextvar set here is guaranteed
    to still be visible to everything downstream -- including sync route
    handlers, which FastAPI dispatches via `anyio.to_thread.run_sync`
    (which itself copies the calling task's `contextvars.Context` into the
    worker thread). `BaseHTTPMiddleware` has historically had exactly this
    kind of contextvar-propagation footgun because of how it wraps
    `call_next`; a bare ASGI middleware sidesteps the question entirely.

    One run/request id per HTTP request, bound into
    `app.observability.events`'s contextvar for the lifetime of that
    request: every `app.utils.logging.get_logger(...)` log line and every
    `RunEvent` a traced graph node emits during this request carries it.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.lower().encode("latin-1"))
        run_id = incoming.decode("latin-1") if incoming else new_run_id()
        token = set_run_id(run_id)

        async def send_with_request_id(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.append(
                    (REQUEST_ID_HEADER.encode("latin-1"), run_id.encode("latin-1"))
                )
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_run_id(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail closed BEFORE the app can serve traffic if SESSION_SECRET is
    # missing outside local dev -- see app.dependencies for the signal
    # used to detect local dev and why raising here (not warning) matters.
    validate_session_secret_at_startup()
    init_db()
    yield
    # OpenTelemetry shutdown/flush (ROADMAP.md Phase 1, Step 1.3) -- this
    # function had no shutdown code at all before this: a no-op when
    # tracing was never enabled (app.observability.tracing.shutdown_tracing
    # checks that itself), otherwise flushes any spans still buffered in
    # the BatchSpanProcessor before the process exits so they aren't
    # silently dropped. NOTE: OTel initialization itself happens earlier,
    # synchronously in create_app() below -- NOT here -- see that call
    # site's comment for why.
    shutdown_tracing()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MacroChef Agent",
        description="A multimodal, constraint-aware meal planning system.",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Request-id tracing (ROADMAP.md Phase 1, Step 1.1) -- added first so it
    # ends up the innermost layer wrapping the router (Starlette wraps
    # middleware in reverse add-order, so the LAST-added middleware sits
    # outermost); relative order vs CORSMiddleware doesn't functionally
    # matter here since every route that needs `run_id` is inside both, but
    # keeping it added before CORS keeps this list in "most fundamental
    # first" order.
    app.add_middleware(RequestIdMiddleware)
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
    app.include_router(admin_router)

    # LAST: mounts the built SPA (if present) + its catch-all client-routing
    # fallback. Must stay after every app.include_router(...) call above --
    # see app/spa.py's module docstring for why ordering matters here.
    mount_spa(app)

    # OpenTelemetry tracing (ROADMAP.md Phase 1, Step 1.3) -- called here,
    # synchronously during app construction, NOT from inside `lifespan`
    # above: FastAPIInstrumentor.instrument_app monkeypatches
    # `app.build_middleware_stack`, and Starlette caches that method's
    # result on the very first ASGI `__call__` regardless of scope type --
    # including the `lifespan` scope itself, which runs BEFORE our
    # `lifespan()` function's body starts executing. Calling this from
    # inside `lifespan()` would therefore silently fail to instrument the
    # app. A true no-op (no SDK provider constructed, no FastAPI/requests
    # instrumentation installed) when OTEL_EXPORTER_OTLP_ENDPOINT is unset
    # -- see app.observability.tracing's module docstring.
    init_tracing(app)

    return app


app = create_app()
