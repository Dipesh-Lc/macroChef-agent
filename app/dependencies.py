from collections.abc import Callable, Generator

from fastapi import Depends, Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings, get_settings
from app.data.db import SessionLocal
from app.services.rate_limiter import get_rate_limiter
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Header the (trusted) Streamlit frontend sends the signed session token on,
# and the API verifies on every /library request. Never a request body /
# path field -- see get_session_user.
SESSION_TOKEN_HEADER = "X-Session-Token"

# 30 days: an anonymous library session is long-lived by design (no login),
# but not forever -- an expired token forces a fresh (empty) anonymous
# session rather than living indefinitely.
SESSION_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

# itsdangerous salt namespacing this token from any other signed value that
# might someday share the same secret.
_SESSION_TOKEN_SALT = "macrochef-session-v1"

# Settings.session_secret defaults to None until a human sets SESSION_SECRET
# (see .env.example / ACA secrets). This fixed, obviously-fake string is the
# ONLY value ever returned in place of a real secret, and only when a human
# has explicitly opted in via `allow_insecure_session_secret`
# (ALLOW_INSECURE_SESSION_SECRET=1) -- there is deliberately no heuristic
# (e.g. sniffing DATABASE_URL) that turns this on automatically, because an
# unrelated setting silently drifting (or simply defaulting) must never
# decide a security outcome. This is a deliberate, narrow exception to
# "never hardcode a secret" -- it is not a real secret, it's a dev-only
# placeholder, and reaching it always logs a loud warning.
#
# Default (secret unset, flag unset) is fail-closed: `_resolve_session_secret`
# raises, so both the FastAPI process (via `validate_session_secret_at_startup`
# at boot) and the Streamlit process (which also mints tokens, via this same
# function) refuse to mint or verify a token signed with a hardcoded default.
_DEV_INSECURE_SESSION_SECRET = "dev-insecure-session-secret-change-me"


def get_app_settings() -> Settings:
    return get_settings()


def get_db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def validate_session_secret_at_startup(settings: Settings | None = None) -> None:
    """Fail closed, at process startup, if SESSION_SECRET is unset and
    ALLOW_INSECURE_SESSION_SECRET is not explicitly set -- called from
    `app.main`'s startup event, BEFORE the app is able to serve any traffic.

    This is deliberately not lazy (i.e. not deferred to the first request
    via `_resolve_session_secret`): a container that boots without a real
    secret must never accept a single request that mints or verifies a
    token signed with the hardcoded dev default -- raising here stops
    uvicorn from starting at all, rather than serving traffic and merely
    logging a warning.

    Delegates to `_resolve_session_secret` so FastAPI (this function, at
    boot) and Streamlit (which calls `_resolve_session_secret` directly on
    every token mint) enforce the exact same rule -- there is only one
    place this decision is made.
    """
    settings = settings or get_app_settings()
    _resolve_session_secret(settings)


def _resolve_session_secret(settings: Settings) -> str:
    """Resolve the secret used to sign/verify session tokens.

    Fail-closed by design: a missing SESSION_SECRET raises unless a human
    has explicitly set ALLOW_INSECURE_SESSION_SECRET (localhost-only escape
    hatch). This is never inferred from database_url or any other setting --
    insecurity must be requested, not guessed at.
    """
    secret = getattr(settings, "session_secret", None)
    if secret:
        return secret
    if getattr(settings, "allow_insecure_session_secret", False):
        logger.warning(
            "SESSION_SECRET is not configured; ALLOW_INSECURE_SESSION_SECRET "
            "is set, so falling back to a hardcoded, publicly-known "
            "development default. This must NEVER happen in a deployed "
            "environment -- anyone who knows the default could forge a "
            "session token. Set SESSION_SECRET and unset "
            "ALLOW_INSECURE_SESSION_SECRET before deploying publicly."
        )
        return _DEV_INSECURE_SESSION_SECRET
    raise RuntimeError(
        "SESSION_SECRET is not set. Refusing to mint or verify session "
        "tokens signed with the hardcoded dev-only default. Set the "
        "SESSION_SECRET environment variable (see .env.example) before "
        "starting this process. If this is a bare local checkout and you "
        "understand the risk, you may instead set "
        "ALLOW_INSECURE_SESSION_SECRET=1 -- localhost-only, never in a "
        "deployed environment."
    )


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_resolve_session_secret(settings), salt=_SESSION_TOKEN_SALT)


def mint_session_token(user_id: str, settings: Settings | None = None) -> str:
    """Sign an anonymous user id into an opaque, timestamped token.

    Called by the Streamlit frontend (never by a route handler acting on
    untrusted input) to mint a token for a brand-new browser session. The
    token is signed, not encrypted -- `user_id` is a random opaque id
    (`secrets.token_urlsafe`), not a secret itself; the signature only makes
    the token unforgeable and tamper-evident.
    """
    settings = settings or get_app_settings()
    return _serializer(settings).dumps(user_id)


def get_session_user(
    x_session_token: str | None = Header(default=None, alias=SESSION_TOKEN_HEADER),
    settings: Settings = Depends(get_app_settings),
) -> str:
    """Derive the caller's anonymous user id from a signed, time-limited
    session token -- the sole source of truth for "who is this request
    from" on every /library route.

    This is the load-bearing check: the API is on localhost behind Streamlit
    in production, but that must never be the only thing protecting user
    data, so a client-supplied user id is never trusted, and a missing,
    forged, tampered, or expired token is always rejected with 401 rather
    than silently treated as a new anonymous session (that would let a
    dropped/corrupted token silently orphan a user's library instead of
    failing loudly).
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing session token")

    serializer = _serializer(settings)
    try:
        user_id = serializer.loads(x_session_token, max_age=SESSION_TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise HTTPException(status_code=401, detail="Session token expired") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="Invalid session token") from exc

    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid session token")
    return user_id


# ---------------------------------------------------------------------------
# Rate limiting -- see app/services/rate_limiter.py for the in-memory,
# per-process implementation and its single-replica assumption.
#
# Every limiter dependency below first resolves `get_session_user`, so an
# unauthenticated caller is rejected 401 before any rate-limit bookkeeping
# happens, and the limiter key is always the verified session user id --
# never a client-supplied value. FastAPI caches a dependency's result per
# request (by callable identity), so a route that also takes
# `Depends(get_session_user)` directly does not re-verify the token twice.
# ---------------------------------------------------------------------------


def _rate_limit_dependency(
    bucket: str,
    limit_getter: Callable[[Settings], int],
    window_getter: Callable[[Settings], float],
) -> Callable[..., str]:
    """Build a FastAPI dependency that 429s once the verified session user
    exceeds `limit_getter(settings)` calls to `bucket` within
    `window_getter(settings)` seconds, and otherwise returns the user id
    (so it can also stand in for `Depends(get_session_user)` on the route)."""

    def _dependency(
        user_id: str = Depends(get_session_user),
        settings: Settings = Depends(get_app_settings),
    ) -> str:
        limit = limit_getter(settings)
        window_seconds = window_getter(settings)
        key = f"{bucket}:{user_id}"
        if not get_rate_limiter().allow(key, limit, window_seconds):
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded: max {limit} requests per "
                    f"{int(window_seconds)}s for this session. Try again later."
                ),
            )
        return user_id

    return _dependency


require_discover_rate_limit = _rate_limit_dependency(
    "library_discover",
    lambda settings: settings.rate_limit_discover_max,
    lambda settings: settings.rate_limit_discover_window_seconds,
)

require_recommend_rate_limit = _rate_limit_dependency(
    "recipes_recommend",
    lambda settings: settings.rate_limit_recommend_max,
    lambda settings: settings.rate_limit_recommend_window_seconds,
)

require_reindex_rate_limit = _rate_limit_dependency(
    "library_reindex",
    lambda settings: settings.rate_limit_reindex_max,
    lambda settings: settings.rate_limit_reindex_window_seconds,
)
