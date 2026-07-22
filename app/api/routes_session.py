"""POST /session -- anonymous session mint/validate endpoint (SPA rebuild,
roadmap item W0).

This is the ONLY HTTP-reachable way to obtain an `mc_session` cookie: it
either confirms a session the caller already has (no rotation, no
Set-Cookie -- see the module docstring in frontend/session_client.py for
the Max-Age-drift bug this deliberately avoids repeating) or mints a brand
new one. Deliberately pre-identity: it must be reachable by a caller with
no session at all, so it is gated by a per-IP rate limit
(`require_session_mint_rate_limit`), never `app.dependencies.
get_session_user` (which would be circular -- the whole point of this
endpoint is to hand out that identity in the first place).

CSRF-exempt by design: unlike every other session-authenticated route
(see `app.dependencies.get_session_user`'s cookie-path CSRF check), this
endpoint never requires `X-Requested-With`. A CSRF'd call here can only
either (a) confirm a session the victim already has -- no state change --
or (b) mint a brand new, otherwise-inert anonymous session and set it as a
cookie in the victim's own browser -- harmless to the victim (it does not
read or leak anything, and the attacker gains no access to the resulting
session since the Set-Cookie response never reaches the attacker's
origin).

No LLM anywhere on this path; no safety/nutrition decision is made here.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import Settings
from app.dependencies import (
    SESSION_COOKIE_NAME,
    SESSION_TOKEN_HEADER,
    SESSION_TOKEN_MAX_AGE_SECONDS,
    get_app_settings,
    mint_session_token,
    resolve_cookie_secure,
    try_decode_session_token,
)
from app.services.analytics import get_analytics
from app.services.rate_limiter import get_rate_limiter
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["session"])


def _session_mint_caller_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_session_mint_rate_limit(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> str:
    """FastAPI dependency gating POST /session by caller IP -- mirrors
    `app.dependencies.require_safety_tools_rate_limit`'s caller-IP pattern
    (NOT the per-session-user pattern the rest of app.dependencies uses),
    because this endpoint is pre-identity by definition: a caller with no
    session at all (the exact caller this endpoint exists for) has no
    verified user id yet to key a per-session limiter on. Same accepted
    limitation as every other caller-IP-keyed limiter in this app: spoofable
    behind a shared NAT/proxy, an abuse guard rather than a security
    boundary (see app.dependencies module-level note for the full
    reasoning). ALL calls count against this bucket uniformly, including
    the 204-no-mint ("already has a valid session") branch -- there is no
    reason to let an already-authenticated caller hammer this endpoint for
    free just because it happens not to mint anything that time.
    """
    caller_id = _session_mint_caller_id(request)
    limit = settings.rate_limit_session_max
    window_seconds = settings.rate_limit_session_window_seconds
    key = f"session_mint:{caller_id}"
    if not get_rate_limiter().allow(key, limit, window_seconds):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {limit} requests per "
                f"{int(window_seconds)}s per caller. Try again later."
            ),
        )
    return caller_id


def _track_event_best_effort(user_id: str, event: str) -> None:
    """Fire a PostHog event for this mint/validate call without letting any
    analytics failure affect the response -- `distinct_id` is always the
    verified inner user id (never the raw signed token string). PostHog
    itself already swallows its own capture errors (see
    app.services.analytics.PostHogAnalytics.capture); this wraps the whole
    call site too, defensively, since this is the one place analytics is on
    a hot, session-critical path rather than a fire-and-forget side effect
    of an already-succeeded write.
    """
    try:
        get_analytics().capture(user_id, event, {})
    except Exception:
        logger.warning(
            "session analytics capture failed for event %r", event, exc_info=True
        )


@router.post("/session", status_code=204)
def mint_or_validate_session(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_app_settings),
    _caller_id: str = Depends(require_session_mint_rate_limit),
) -> None:
    """Confirm an existing valid session (204, no Set-Cookie, no rotation)
    or mint a brand-new one (204 + Set-Cookie).

    Reads BOTH possible existing-session carriers directly (never via
    `app.dependencies.get_session_user`, which enforces the CSRF header
    check this endpoint deliberately does not apply): the `X-Session-Token`
    header first, then the `mc_session` cookie -- an invalid/expired value
    on either is treated exactly like "absent" here (mint fresh), never as
    an error, since minting a new anonymous session is always a safe,
    always-available fallback for this endpoint.
    """
    header_token = request.headers.get(SESSION_TOKEN_HEADER)
    user_id = try_decode_session_token(header_token, settings) if header_token else None
    if user_id is None:
        cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
        if cookie_token:
            user_id = try_decode_session_token(cookie_token, settings)

    if user_id is not None:
        # Already has a valid session -- confirm it as-is. Deliberately NO
        # Set-Cookie here: rewriting/rotating an already-valid cookie on
        # every call is exactly the Max-Age-drift bug
        # frontend/session_client.py's module docstring documents fixing on
        # the Streamlit side; this endpoint must not reintroduce it.
        _track_event_best_effort(user_id, "return visit")
        return None

    new_user_id = secrets.token_urlsafe(32)
    token = mint_session_token(new_user_id, settings)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TOKEN_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        secure=resolve_cookie_secure(request, settings),
        samesite="lax",
    )
    # The token itself never appears in the response body -- only ever in
    # the Set-Cookie header above.
    _track_event_best_effort(new_user_id, "new visitor")
    return None
