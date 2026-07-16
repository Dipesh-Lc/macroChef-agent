"""Regression tests for `frontend/session_client.py`'s 401/expiry recovery.

Advisor finding (MEDIUM-HIGH, a ~30-day time bomb): the old
`get_session_token` trusted ANY cookie value it found
(`_existing_cookie_token() or _mint_new_token()`), and `reset_session_token`
only popped `st.session_state` -- it never touched the cookie. So roughly
30 days after a user's first visit, their token's itsdangerous signature
expires, the API starts returning 401 forever, and the "recovery" path fed
the exact same dead cookie value right back in on every retry. The user was
locked out until they manually cleared cookies.

These tests exercise the real production functions (`get_session_token`,
`reset_session_token`, `_token_is_valid`) -- not a reimplementation -- and
were confirmed to FAIL against the pre-fix version of
`frontend/session_client.py` before the fix in this same task was applied
(see the task report for the confirmation transcript). They:

  1. Feed a genuinely EXPIRED token (signed with a backdated itsdangerous
     timestamp -- no `sleep(30 days)` involved) into the cookie and assert
     the client converges to a *different*, freshly-valid token instead of
     looping on the dead one.
  2. Feed an INVALID/tampered cookie token (corrupted signature) and assert
     the same convergence.
  3. Feed a VALID, non-expired token and assert it is reused as-is (not
     needlessly re-minted, and the cookie is not rewritten) -- so the fix
     doesn't "fix" the bug by nuking every session on every load, which
     would silently log everyone out constantly and would pass a naive
     expiry-only test.

Settings are always injected explicitly (`monkeypatch.setenv("SESSION_SECRET",
...)` + `get_settings.cache_clear()`) -- never relying on ambient `.env`
config, which is absent in CI and would make these tests non-portable.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from itsdangerous import TimestampSigner

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from app.config import get_settings  # noqa: E402
from app.dependencies import SESSION_TOKEN_MAX_AGE_SECONDS, _serializer  # noqa: E402

import session_client  # noqa: E402

_TEST_SECRET = "test-only-session-secret-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _explicit_session_secret(monkeypatch: pytest.MonkeyPatch):
    """Every test in this module gets an explicit, known SESSION_SECRET --
    never the ambient `.env` (absent in CI) and never the fail-closed
    "unset" default that would make `mint_session_token`/`_serializer`
    raise. `get_settings.cache_clear()` mirrors the pattern in
    `tests/conftest.py`'s `force_mock_model_provider` fixture."""
    monkeypatch.setenv("SESSION_SECRET", _TEST_SECRET)
    monkeypatch.delenv("ALLOW_INSECURE_SESSION_SECRET", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clean_streamlit_session_state():
    """`st.session_state` is a process-global singleton outside of a real
    Streamlit script run (there is no per-test isolation Streamlit gives
    us for free), so each test starts and ends with it cleared to avoid
    cross-test pollution."""
    session_client.st.session_state.clear()
    yield
    session_client.st.session_state.clear()


@pytest.fixture(autouse=True)
def _stub_browser_cookie_write(monkeypatch: pytest.MonkeyPatch):
    """Replace the real cookie-writing side effect (a `components.html`
    injection, meaningless outside a browser) with a spy that records what
    would have been written, so tests can assert on cookie-overwrite
    behavior without a real browser."""
    written: list[str] = []
    monkeypatch.setattr(session_client, "_set_browser_cookie", lambda token: written.append(token))
    return written


def _mint_token(session_id: str = "test-session-id") -> str:
    """Mint a token exactly the way `session_client._mint_new_token` does,
    via the real settings/serializer -- a normal, currently-valid token."""
    return session_client.mint_session_token(session_id, get_settings())


def _mint_token_signed_seconds_ago(seconds_ago: int, session_id: str = "test-session-id") -> str:
    """Mint a token whose itsdangerous timestamp is backdated by
    `seconds_ago`, using the exact same serializer construction the app
    uses (`app.dependencies._serializer`). This produces a genuinely
    expired signature under `max_age` verification without sleeping -- the
    signer's `unsign` computes `age = get_timestamp() - stored_ts`, so
    backdating the timestamp at signing time (via monkeypatching
    `TimestampSigner.get_timestamp` for the duration of the `dumps` call
    only) is equivalent to having actually signed it that long ago.
    """
    real_get_timestamp = TimestampSigner.get_timestamp
    backdated = int(time.time()) - seconds_ago
    TimestampSigner.get_timestamp = lambda self: backdated  # type: ignore[method-assign]
    try:
        return _serializer(get_settings()).dumps(session_id)
    finally:
        TimestampSigner.get_timestamp = real_get_timestamp  # type: ignore[method-assign]


def test_expired_cookie_signature_is_genuinely_expired_under_max_age():
    """Sanity check on the test helper itself: the backdated token really
    does fail the server's own `max_age` check (not just "looks old")."""
    expired = _mint_token_signed_seconds_ago(SESSION_TOKEN_MAX_AGE_SECONDS + 3600)
    with pytest.raises(Exception):
        _serializer(get_settings()).loads(expired, max_age=SESSION_TOKEN_MAX_AGE_SECONDS)


class TestExpiredCookieConvergesToFreshSession:
    def test_get_session_token_replaces_expired_cookie(self, monkeypatch):
        expired = _mint_token_signed_seconds_ago(SESSION_TOKEN_MAX_AGE_SECONDS + 3600)
        monkeypatch.setattr(session_client, "_existing_cookie_token", lambda: expired)

        token = session_client.get_session_token()

        assert token != expired
        assert session_client._token_is_valid(token)
        # Cached, so a second call in the same "browser session" doesn't
        # re-derive or re-mint again.
        assert session_client.get_session_token() == token

    def test_reset_session_token_after_401_does_not_loop_on_dead_cookie(self, monkeypatch):
        """Simulates the exact failure mode described in the task: the
        cookie already holds a dead token when the API 401s. The old
        `reset_session_token` only popped `st.session_state`, so the very
        next `get_session_token()` call read the same dead cookie right
        back out via `_existing_cookie_token()`. Confirmed to fail against
        that pre-fix code (see report)."""
        expired = _mint_token_signed_seconds_ago(SESSION_TOKEN_MAX_AGE_SECONDS + 3600)
        monkeypatch.setattr(session_client, "_existing_cookie_token", lambda: expired)
        session_client.st.session_state[session_client._STATE_KEY] = expired

        new_token = session_client.reset_session_token()

        assert new_token != expired
        assert session_client._token_is_valid(new_token)
        # get_session_token must now return the freshly reset token, not
        # fall back to re-reading the (still-expired) cookie stub.
        assert session_client.get_session_token() == new_token


class TestInvalidCookieConvergesToFreshSession:
    def test_get_session_token_replaces_tampered_cookie(self, monkeypatch):
        valid = _mint_token()
        tampered = valid[:-1] + ("A" if valid[-1] != "A" else "B")
        monkeypatch.setattr(session_client, "_existing_cookie_token", lambda: tampered)

        token = session_client.get_session_token()

        assert token != tampered
        assert session_client._token_is_valid(token)

    def test_token_is_valid_rejects_garbage(self):
        assert session_client._token_is_valid("not-a-real-token-at-all") is False


class TestValidCookieIsReusedNotReminted:
    def test_get_session_token_reuses_valid_cookie_without_rewriting_it(
        self, monkeypatch, _stub_browser_cookie_write
    ):
        valid = _mint_token()
        monkeypatch.setattr(session_client, "_existing_cookie_token", lambda: valid)

        token = session_client.get_session_token()

        assert token == valid
        # The whole point of the fix: a still-valid cookie must be reused
        # as-is, not silently replaced -- a naive "always mint fresh on
        # load" fix would pass an expiry-only test but would log every
        # returning user out on every rerun.
        assert _stub_browser_cookie_write == []

    def test_get_session_token_is_idempotent_across_calls(self, monkeypatch):
        valid = _mint_token()
        monkeypatch.setattr(session_client, "_existing_cookie_token", lambda: valid)

        first = session_client.get_session_token()
        second = session_client.get_session_token()

        assert first == second == valid
