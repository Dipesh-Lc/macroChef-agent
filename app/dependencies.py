from collections.abc import Generator

from fastapi import Depends, Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings, get_settings
from app.data.db import SessionLocal
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
# (see .env.example / ACA secrets). Falling back to a fixed, obviously-fake
# string keeps local dev and tests working without a real secret configured,
# while still failing loudly (via a warning) that production must override
# it. This is a deliberate, narrow exception to "never hardcode a secret" --
# it is not a real secret, it's a dev-only placeholder that must never be
# reachable from a publicly deployed instance.
_DEV_INSECURE_SESSION_SECRET = "dev-insecure-session-secret-change-me"


def get_app_settings() -> Settings:
    return get_settings()


def get_db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_session_secret(settings: Settings) -> str:
    secret = getattr(settings, "session_secret", None)
    if secret:
        return secret
    logger.warning(
        "SESSION_SECRET is not configured; falling back to an insecure "
        "development default. Set SESSION_SECRET before deploying publicly "
        "-- anyone who knows the default could forge a session token."
    )
    return _DEV_INSECURE_SESSION_SECRET


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
