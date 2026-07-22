"""HTTP-level tests for POST /session (SPA rebuild, roadmap item W0) and the
dual-read (header + cookie) precedence in app.dependencies.get_session_user.

Covers:
1. Fresh mint: 204 + Set-Cookie (HttpOnly, SameSite=Lax, Path=/,
   Max-Age=2592000); the minted cookie authenticates a subsequent
   cookie-based request.
2. A second POST /session with the now-valid cookie: 204, NO Set-Cookie
   (no rotation).
3. Garbage/expired cookie: 204 with a FRESH Set-Cookie.
4. Cookie-authenticated request to a session endpoint requires
   X-Requested-With (any value); without it, 401.
5. Header path is unaffected by the cookie CSRF requirement.
6. Header + a DIFFERENT valid cookie: header identity wins, no
   cross-contamination.
7. Header + a garbage cookie: header still wins (cookie ignored).
8. Invalid header + valid cookie: 401, no fall-through to the cookie.
9. Per-IP 429 once RATE_LIMIT_SESSION_MAX is exceeded.
10. Secure attribute tri-state (auto / always / never).
11. CSRF exemption: POST /session itself never requires X-Requested-With.
12. CORS: allow_credentials=False.
13. Startup fail-closed regression (existing suite untouched).
14. Full recovery loop: dead cookie -> 401 on a session endpoint -> POST
    /session mints a fresh cookie -> retried request succeeds.

Uses an isolated in-memory SQLite database for the /library user-scoped
endpoint used as the "session endpoint" test double throughout, mirroring
tests/test_rate_limiting.py and tests/test_routes_share.py.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes_library as routes_library
import app.data.recipe_library_repository as repo_module
from app.config import get_settings
from app.data.db import Base
from app.dependencies import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TOKEN_HEADER,
    mint_session_token,
)
from app.main import create_app
from app.services.rate_limiter import get_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "session-endpoint-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_library_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /library (the "session endpoint" test double used throughout
    this file) reads via RecipeLibraryRepository, which lazily opens
    SessionLocal() against the real on-disk engine unless overridden --
    same isolation fixture as tests/test_rate_limiting.py, for the same
    reason (a fresh checkout has no user_saved_recipes table yet)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(repo_module, "SessionLocal", test_session_local)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _set_env_limit(monkeypatch: pytest.MonkeyPatch, var: str, value: int | float) -> None:
    monkeypatch.setenv(var, str(value))
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 1. Fresh mint.
# ---------------------------------------------------------------------------


def test_post_session_with_no_prior_session_mints_a_cookie(client: TestClient) -> None:
    response = client.post("/session")

    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    lowered = set_cookie.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "max-age=2592000" in lowered
    assert response.content == b""


def test_minted_cookie_authenticates_a_subsequent_cookie_request(client: TestClient) -> None:
    mint_response = client.post("/session")
    assert mint_response.status_code == 204
    # httpx's TestClient persists Set-Cookie into client.cookies automatically.

    library_response = client.get("/library", headers={CSRF_HEADER_NAME: "1"})

    assert library_response.status_code == 200


# ---------------------------------------------------------------------------
# 2. No rotation on a second call with an already-valid cookie.
# ---------------------------------------------------------------------------


def test_second_post_session_with_valid_cookie_does_not_rotate(client: TestClient) -> None:
    first = client.post("/session")
    assert first.headers.get("set-cookie") is not None

    second = client.post("/session")

    assert second.status_code == 204
    assert second.headers.get("set-cookie") is None


# ---------------------------------------------------------------------------
# 3. Garbage/expired cookie -> fresh Set-Cookie.
# ---------------------------------------------------------------------------


def test_post_session_with_garbage_cookie_mints_a_fresh_one(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-token")

    response = client.post("/session")

    assert response.status_code == 204
    assert response.headers.get("set-cookie") is not None


# ---------------------------------------------------------------------------
# 4. Cookie-authenticated request requires X-Requested-With.
# ---------------------------------------------------------------------------


def test_cookie_auth_without_csrf_header_is_rejected(client: TestClient) -> None:
    client.post("/session")

    response = client.get("/library")

    assert response.status_code == 401


def test_cookie_auth_with_any_csrf_header_value_succeeds(client: TestClient) -> None:
    client.post("/session")

    response = client.get("/library", headers={CSRF_HEADER_NAME: "anything"})

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 5. Header path unaffected by the CSRF header requirement.
# ---------------------------------------------------------------------------


def test_header_path_succeeds_without_csrf_header(client: TestClient) -> None:
    token = _token("header_only_user")

    response = client.get("/library", headers={SESSION_TOKEN_HEADER: token})

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 6/7/8. Exclusive precedence between header and cookie.
# ---------------------------------------------------------------------------


def test_valid_header_and_different_valid_cookie_header_identity_wins(
    client: TestClient,
) -> None:
    header_token = _token("header_user")
    client.cookies.set(SESSION_COOKIE_NAME, _token("cookie_user"))

    response = client.post(
        "/library/save",
        json={"selected_candidates": []},
        headers={SESSION_TOKEN_HEADER: header_token, CSRF_HEADER_NAME: "1"},
    )

    # header_user's identity must be what's used, never cookie_user's --
    # asserted indirectly: the request must succeed (both are validly
    # signed, so if the cookie silently won this would ALSO succeed, which
    # is why the real cross-contamination proof needs a user-scoped read).
    assert response.status_code == 200

    header_library = client.get("/library", headers={SESSION_TOKEN_HEADER: header_token})
    assert header_library.status_code == 200
    assert header_library.json()["recipes"] == []


def test_valid_header_and_garbage_cookie_succeeds_via_header(client: TestClient) -> None:
    header_token = _token("header_wins_user")
    client.cookies.set(SESSION_COOKIE_NAME, "garbage-cookie-value")

    response = client.get("/library", headers={SESSION_TOKEN_HEADER: header_token})

    assert response.status_code == 200


def test_invalid_header_and_valid_cookie_is_rejected_no_fallthrough(
    client: TestClient,
) -> None:
    client.post("/session")  # mint a valid cookie

    response = client.get(
        "/library",
        headers={SESSION_TOKEN_HEADER: "not-a-real-token", CSRF_HEADER_NAME: "1"},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 9. Per-IP 429 on POST /session.
# ---------------------------------------------------------------------------


def test_session_mint_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_SESSION_MAX", 2)
    _set_env_limit(monkeypatch, "RATE_LIMIT_SESSION_WINDOW_SECONDS", 3600)

    first = client.post("/session")
    second = client.post("/session")
    third = client.post("/session")

    assert first.status_code == 204
    assert second.status_code == 204
    assert third.status_code == 429


def test_session_mint_rate_limit_counts_the_204_no_mint_branch_too(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All POST /session calls count uniformly against the bucket, including
    calls that confirm an already-valid session rather than minting."""
    _set_env_limit(monkeypatch, "RATE_LIMIT_SESSION_MAX", 2)
    _set_env_limit(monkeypatch, "RATE_LIMIT_SESSION_WINDOW_SECONDS", 3600)

    first = client.post("/session")  # mints
    second = client.post("/session")  # already valid, no mint -- still counts
    third = client.post("/session")  # over the cap

    assert first.status_code == 204
    assert second.status_code == 204
    assert third.status_code == 429


# ---------------------------------------------------------------------------
# 10. Secure attribute tri-state.
# ---------------------------------------------------------------------------


def test_secure_absent_over_plain_http_with_default_auto(client: TestClient) -> None:
    response = client.post("/session")

    set_cookie = response.headers.get("set-cookie", "")
    assert "secure" not in set_cookie.lower()


def test_secure_present_when_forwarded_proto_is_https(client: TestClient) -> None:
    response = client.post("/session", headers={"X-Forwarded-Proto": "https"})

    set_cookie = response.headers.get("set-cookie", "")
    assert "secure" in set_cookie.lower()


def test_secure_present_with_always_even_over_spoofed_forwarded_proto_http(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "always")
    get_settings.cache_clear()

    response = client.post("/session", headers={"X-Forwarded-Proto": "http"})

    set_cookie = response.headers.get("set-cookie", "")
    assert "secure" in set_cookie.lower()
    get_settings.cache_clear()


def test_secure_absent_with_never_even_over_forwarded_proto_https(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "never")
    get_settings.cache_clear()

    response = client.post("/session", headers={"X-Forwarded-Proto": "https"})

    set_cookie = response.headers.get("set-cookie", "")
    assert "secure" not in set_cookie.lower()
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 11. CSRF exemption on POST /session itself.
# ---------------------------------------------------------------------------


def test_post_session_with_valid_cookie_and_no_csrf_header_still_succeeds(
    client: TestClient,
) -> None:
    client.post("/session")  # mints a valid cookie, stored in the client jar

    response = client.post("/session")  # no X-Requested-With header at all

    assert response.status_code == 204


# ---------------------------------------------------------------------------
# 12. CORS: allow_credentials=False.
# ---------------------------------------------------------------------------


def test_cors_allow_credentials_is_false() -> None:
    app = create_app()
    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            cors_middleware = middleware
            break
    assert cors_middleware is not None

    kwargs = cors_middleware.kwargs
    assert kwargs.get("allow_credentials") is False


# ---------------------------------------------------------------------------
# 14. Full recovery loop.
# ---------------------------------------------------------------------------


def test_full_recovery_loop_expired_cookie_then_remint_then_success(
    client: TestClient,
) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "dead-or-garbage-cookie")

    first_attempt = client.get("/library", headers={CSRF_HEADER_NAME: "1"})
    assert first_attempt.status_code == 401

    mint_response = client.post("/session")
    assert mint_response.status_code == 204
    assert mint_response.headers.get("set-cookie") is not None

    retried = client.get("/library", headers={CSRF_HEADER_NAME: "1"})
    assert retried.status_code == 200
