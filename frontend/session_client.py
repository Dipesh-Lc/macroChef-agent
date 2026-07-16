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
"""

import secrets

import requests
import streamlit as st

from app.config import get_settings
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token

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


def get_session_token() -> str:
    """Return this browser's signed anonymous session token, minting (and
    persisting) a new one on first visit. Cached in `st.session_state` so
    repeated reruns within the same browser session don't re-mint or
    re-write the cookie on every interaction."""
    cached = st.session_state.get(_STATE_KEY)
    if cached:
        return cached

    token = _existing_cookie_token() or _mint_new_token()
    st.session_state[_STATE_KEY] = token
    _set_browser_cookie(token)
    return token


def reset_session_token() -> None:
    """Drop the cached/cookie token so the next call to `get_session_token`
    mints a fresh anonymous session -- used after the API rejects a token
    with 401 (e.g. an expired or forged token) so the user gets a working,
    if empty, session instead of being stuck."""
    st.session_state.pop(_STATE_KEY, None)


def session_headers() -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: get_session_token()}


def request_with_session(method: str, url: str, **kwargs) -> requests.Response:
    """`requests.request` with the session header attached, retried once
    with a freshly minted token if the API returns 401 (expired/forged
    token) rather than surfacing an opaque failure."""
    extra_headers = kwargs.pop("headers", {}) or {}
    response = requests.request(
        method, url, headers={**extra_headers, **session_headers()}, **kwargs
    )
    if response.status_code == 401:
        reset_session_token()
        response = requests.request(
            method, url, headers={**extra_headers, **session_headers()}, **kwargs
        )
    return response
