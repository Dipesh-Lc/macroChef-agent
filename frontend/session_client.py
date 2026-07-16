"""Anonymous browser-session handling for the Streamlit frontend.

The API (app.dependencies.get_session_user) is the sole authority on WHO a
request is from -- it verifies the signature and expiry of the token this
module sends and never trusts anything else. This module only mints an
opaque, signed token for a first-time visitor and best-effort persists it in
a browser cookie so a returning visitor keeps the same anonymous library.
Nothing here needs to be trusted for the isolation guarantee to hold: a
forged or tampered token is rejected by the API regardless of what a
compromised or buggy frontend sends.

Known limitation (see task report): Streamlit's script-rerun execution model
has no supported way to attach a `Set-Cookie` response header to an ordinary
page rerun (only the very first, unscripted page load is a normal HTTP
response/request cycle), so the cookie set here cannot be marked HttpOnly.
`Secure` and `SameSite=Lax` are set from JS; `Secure` is dropped automatically
by browsers on a plain http:// origin so local dev keeps working.

Expiry handling (fixed 2026-07-17, advisor finding -- a ~30-day time bomb):
`get_session_token` used to trust ANY cookie value it found
(`_existing_cookie_token() or _mint_new_token()`) and `reset_session_token`
only cleared `st.session_state`, so the very next `get_session_token` call
read the same dead cookie right back out -- an expired or forged token could
never actually be replaced; the user was 401'd forever. Fixed by locally
verifying the cookie token's signature *and* expiry (`_token_is_valid`,
using the exact same serializer/max_age the API enforces) before ever
trusting it, so a dead cookie is caught and replaced at read time instead of
being re-sent and bounced by the API. `reset_session_token` (the 401
recovery path in `request_with_session`) is hardened to match: it now mints
a fresh token AND overwrites the browser cookie immediately, rather than
merely forgetting the old one, so a 401 for any other reason (e.g. a
rotated SESSION_SECRET) also converges to a working session on the next
request instead of retrying the same value.

This also fixes a latent Max-Age drift: the old code rewrote the cookie
(reset its Max-Age to a fresh 30 days) on every browser session that still
had a cached-but-unwritten token, so the cookie could silently outlive the
token's real, fixed-at-mint-time signature expiry. The cookie is now only
(re)written at the moment a token is actually minted, so its Max-Age and the
token's `max_age` signature window start from the same instant and stay in
sync.
"""

import secrets

import requests
import streamlit as st
from itsdangerous import BadSignature, SignatureExpired

from app.config import get_settings
from app.dependencies import (
    SESSION_TOKEN_HEADER,
    SESSION_TOKEN_MAX_AGE_SECONDS,
    _serializer,  # private, imported deliberately -- see _token_is_valid
    mint_session_token,
)

_COOKIE_NAME = "mc_session"
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days; mirrors the server-side TTL.
_STATE_KEY = "_mc_session_token"


def _mint_new_token() -> str:
    session_id = secrets.token_urlsafe(32)
    return mint_session_token(session_id, get_settings())


def _existing_cookie_token() -> str | None:
    try:
        cookies = st.context.cookies
    except Exception:
        return None
    token = cookies.get(_COOKIE_NAME) if cookies else None
    return token or None


def _set_browser_cookie(token: str) -> None:
    import streamlit.components.v1 as components

    # `components.html` renders inside its own iframe, so a plain
    # `document.cookie` here would set the cookie on the iframe's document,
    # not the top-level page's -- it would never be visible to
    # `st.context.cookies` on the next visit. `window.parent.document.cookie`
    # reaches the actual page document (mirrors the same-origin cookie
    # pattern already used by frontend/streamlit_app.py's analytics
    # return-visit cookie).
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                var isHttps = window.location.protocol === "https:";
                var cookie = "{_COOKIE_NAME}={token}; Max-Age={_COOKIE_MAX_AGE_SECONDS}; "
                    + "path=/; SameSite=Lax";
                if (isHttps) {{ cookie += "; Secure"; }}
                window.parent.document.cookie = cookie;
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _token_is_valid(token: str) -> bool:
    """Verify `token`'s signature AND expiry using the exact serializer/
    max_age the API enforces (`app.dependencies._serializer` /
    `SESSION_TOKEN_MAX_AGE_SECONDS`) -- deliberately the same construction
    the server uses, not a re-implementation, so this can never drift out of
    sync with what `get_session_user` will actually accept.

    Reusing the API's own check here (instead of only reacting to a 401
    after the fact) means a cookie that has aged past its 30-day signature
    expiry is caught and replaced before it is ever sent, rather than being
    re-read from the cookie on every rerun and bounced by the server forever
    (the original bug: `get_session_token` trusted any cookie value it
    found, and `reset_session_token` only cleared session state, so the next
    `get_session_token` call read the very same dead cookie right back out).
    """
    try:
        _serializer(get_settings()).loads(token, max_age=SESSION_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return True


def get_session_token() -> str:
    """Return this browser's signed anonymous session token, minting (and
    persisting) a new one on first visit -- or whenever the existing cookie
    turns out to be expired or invalid. Cached in `st.session_state` so
    repeated reruns within the same browser session don't re-validate,
    re-mint, or re-write the cookie on every interaction.

    A cookie token is only ever reused after passing `_token_is_valid`; an
    expired or tampered one is silently replaced with a fresh anonymous
    session (losing the old, anonymous library is expected -- the
    alternative is a permanent lockout with no way to recover)."""
    cached = st.session_state.get(_STATE_KEY)
    if cached:
        return cached

    existing = _existing_cookie_token()
    if existing and _token_is_valid(existing):
        st.session_state[_STATE_KEY] = existing
        # Not re-written to the cookie: it's already there with the Max-Age
        # it was minted with, and rewriting it here on every fresh browser
        # session would extend the cookie's lifetime past the token's fixed
        # signature expiry (the Max-Age drift noted in the module docstring).
        return existing

    return reset_session_token()


def reset_session_token() -> str:
    """Mint a brand-new anonymous session token, cache it, and overwrite the
    browser cookie immediately -- used both when the existing cookie is
    locally found to be dead (see `get_session_token`) and after the API
    rejects a token with a 401 (e.g. a forged token, or a server-side
    SESSION_SECRET rotation invalidating everything at once).

    Returns the new token so callers can use it immediately without a
    second read of (now up to date) `st.session_state`. Overwriting the
    cookie here -- rather than just forgetting the old token, as the
    previous version did -- is what actually closes the recovery loop: the
    next `get_session_token`/cookie read can no longer find the dead value,
    because it was never left behind."""
    token = _mint_new_token()
    st.session_state[_STATE_KEY] = token
    _set_browser_cookie(token)
    return token


def session_headers() -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: get_session_token()}


def request_with_session(method: str, url: str, **kwargs) -> requests.Response:
    """`requests.request` with the session header attached, retried once
    with a freshly minted (and cookie-persisted) token if the API returns
    401 (expired/forged token, or a secret rotation) rather than surfacing
    an opaque failure or retrying with the same dead token."""
    extra_headers = kwargs.pop("headers", {}) or {}
    response = requests.request(
        method, url, headers={**extra_headers, **session_headers()}, **kwargs
    )
    if response.status_code == 401:
        token = reset_session_token()
        response = requests.request(
            method,
            url,
            headers={**extra_headers, SESSION_TOKEN_HEADER: token},
            **kwargs,
        )
    return response
