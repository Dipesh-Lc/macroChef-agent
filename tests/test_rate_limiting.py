"""Tests for the per-session, in-memory rate limits on the endpoints that
drive paid LLM calls or heavy synchronous work:

- POST /library/discover
- POST /recipes/recommend
- POST /library/reindex (also now requires a verified session at all --
  it previously took none)

See app/services/rate_limiter.py (the sliding-window counter) and
app/dependencies.py (`require_discover_rate_limit`,
`require_recommend_rate_limit`, `require_reindex_rate_limit` -- the
FastAPI dependencies that key it on the verified `get_session_user` id,
never a client-supplied value).
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
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.services.rate_limiter import get_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """The rate limiter is a process-wide singleton (by design -- see
    app.services.rate_limiter.get_rate_limiter); reset it around every test
    so counts from one test never leak into the next."""
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    """Provide an explicit SESSION_SECRET so this suite tests the real
    signing/verification behavior regardless of ambient environment state.

    Without this, `_token()` below mints via the ambient `get_settings()`,
    which only resolves because a developer's local `.env` happens to have
    SESSION_SECRET set -- CI's `test` job sets only EMBEDDING_PROVIDER=hash
    and has no `.env` (gitignored), so `_resolve_session_secret` would raise
    there (see app.dependencies). `get_settings` is `lru_cache`d, so the
    cache must be cleared both before (to pick up the monkeypatched env) and
    after (so a stale Settings instance never leaks into a later test) --
    matches the pattern in tests/conftest.py's `force_mock_model_provider`.
    """
    monkeypatch.setenv("SESSION_SECRET", "rate-limit-test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_library_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """/library/discover reads via RecipeLibraryRepository, which lazily
    opens SessionLocal() against `app.data.db`'s module-level, real on-disk
    engine (default sqlite:///./macrochef.db) unless overridden. The
    `client` fixture below builds `TestClient(create_app())` WITHOUT the
    `with` context manager, so the FastAPI startup hook -- the only place
    `init_db()` is ever called -- never fires here (see
    tests/test_session_secret_startup.py for that distinction). On a
    genuinely fresh checkout (no pre-existing macrochef.db, exactly what
    CI's `test` job starts from), that table has never been created, so the
    discover tests below raise `OperationalError: no such table:
    user_saved_recipes` -- reproduced directly by running this file against
    a fresh sqlite file with EMBEDDING_PROVIDER=hash, matching CI. This was
    previously masked on a dev machine only because a real macrochef.db
    with that table already happens to exist on disk.

    Point the repository at a fresh in-memory SQLite DB instead, mirroring
    the exact same pattern tests/test_recipe_library_isolation.py already
    uses for the same reason -- so these tests never depend on, and never
    mutate, whatever the developer's real macrochef.db happens to contain.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(repo_module, "SessionLocal", test_session_local)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # /library/reindex re-embeds the whole corpus -- stub it out so these
    # rate-limit tests stay fast and don't depend on the real corpus/Chroma
    # being present; the rate limit itself is what's under test here, not
    # the indexing work it gates.
    monkeypatch.setattr(
        routes_library.RecipeIndexingService,
        "rebuild_index",
        lambda self, include_base=True, include_user=True: 0,
    )
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _set_env_limit(monkeypatch: pytest.MonkeyPatch, var: str, value: int | float) -> None:
    monkeypatch.setenv(var, str(value))
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Nth+1 request in the window gets 429.
# ---------------------------------------------------------------------------


def test_discover_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_DISCOVER_MAX", 2)
    _set_env_limit(monkeypatch, "RATE_LIMIT_DISCOVER_WINDOW_SECONDS", 3600)
    headers = _headers("rl_discover_user")

    first = client.post("/library/discover", json={}, headers=headers)
    second = client.post("/library/discover", json={}, headers=headers)
    third = client.post("/library/discover", json={}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_recommend_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_RECOMMEND_MAX", 2)
    _set_env_limit(monkeypatch, "RATE_LIMIT_RECOMMEND_WINDOW_SECONDS", 3600)
    headers = _headers("rl_recommend_user")
    payload = {"user_profile": {}}

    first = client.post("/recipes/recommend", json=payload, headers=headers)
    second = client.post("/recipes/recommend", json=payload, headers=headers)
    third = client.post("/recipes/recommend", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_reindex_nth_plus_one_request_gets_429_using_the_real_default_cap(
    client: TestClient,
) -> None:
    """Deliberately does NOT override RATE_LIMIT_REINDEX_MAX -- proves the
    real shipped default (2) is what gates this endpoint."""
    headers = _headers("rl_reindex_user")

    first = client.post("/library/reindex", headers=headers)
    second = client.post("/library/reindex", headers=headers)
    third = client.post("/library/reindex", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


# ---------------------------------------------------------------------------
# Limits are per-session, not global -- user A exhausting their quota must
# never exhaust user B's (the same isolation property 58053d3 established
# for library data, now proven for rate limiting).
# ---------------------------------------------------------------------------


def test_discover_rate_limit_is_per_session_not_shared_across_users(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_DISCOVER_MAX", 1)
    _set_env_limit(monkeypatch, "RATE_LIMIT_DISCOVER_WINDOW_SECONDS", 3600)
    headers_a = _headers("user_a_rate_limit")
    headers_b = _headers("user_b_rate_limit")

    user_a_first = client.post("/library/discover", json={}, headers=headers_a)
    user_a_second = client.post("/library/discover", json={}, headers=headers_a)
    user_b_first = client.post("/library/discover", json={}, headers=headers_b)

    assert user_a_first.status_code == 200
    assert user_a_second.status_code == 429  # user A is now over their own cap
    assert user_b_first.status_code == 200  # user B's quota is untouched


def test_reindex_rate_limit_is_per_session_not_shared_across_users(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_REINDEX_MAX", 1)
    headers_a = _headers("user_a_reindex")
    headers_b = _headers("user_b_reindex")

    user_a_first = client.post("/library/reindex", headers=headers_a)
    user_a_second = client.post("/library/reindex", headers=headers_a)
    user_b_first = client.post("/library/reindex", headers=headers_b)

    assert user_a_first.status_code == 200
    assert user_a_second.status_code == 429
    assert user_b_first.status_code == 200


# ---------------------------------------------------------------------------
# Reindex: no session at all is rejected (it used to take no dependency),
# and its default cap is the tightest of the three.
# ---------------------------------------------------------------------------


def test_reindex_without_a_session_token_is_rejected_401(client: TestClient) -> None:
    response = client.post("/library/reindex")
    assert response.status_code == 401


def test_discover_without_a_session_token_is_rejected_401_before_rate_limiting(
    client: TestClient,
) -> None:
    response = client.post("/library/discover", json={})
    assert response.status_code == 401


def test_recommend_without_a_session_token_is_rejected_401(client: TestClient) -> None:
    response = client.post("/recipes/recommend", json={"user_profile": {}})
    assert response.status_code == 401


def test_default_reindex_cap_is_tighter_than_discover_and_recommend() -> None:
    """The heaviest endpoint (synchronous full-corpus re-embed) must have the
    smallest default budget of the three."""
    settings = get_settings()
    assert settings.rate_limit_reindex_max < settings.rate_limit_discover_max
    assert settings.rate_limit_reindex_max < settings.rate_limit_recommend_max


# ---------------------------------------------------------------------------
# RateLimiter unit tests (no HTTP layer).
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_up_to_the_limit_then_blocks() -> None:
    from app.services.rate_limiter import RateLimiter

    limiter = RateLimiter()
    assert limiter.allow("k", limit=3, window_seconds=60, now=0.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60, now=1.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60, now=2.0) is True
    assert limiter.allow("k", limit=3, window_seconds=60, now=3.0) is False


def test_rate_limiter_recovers_once_the_window_slides_past_old_hits() -> None:
    from app.services.rate_limiter import RateLimiter

    limiter = RateLimiter()
    assert limiter.allow("k", limit=1, window_seconds=10, now=0.0) is True
    assert limiter.allow("k", limit=1, window_seconds=10, now=5.0) is False
    # 10 seconds later the first hit (at t=0) has aged out of the window.
    assert limiter.allow("k", limit=1, window_seconds=10, now=10.5) is True


def test_rate_limiter_keys_are_independent() -> None:
    from app.services.rate_limiter import RateLimiter

    limiter = RateLimiter()
    assert limiter.allow("user_a", limit=1, window_seconds=60, now=0.0) is True
    assert limiter.allow("user_a", limit=1, window_seconds=60, now=1.0) is False
    assert limiter.allow("user_b", limit=1, window_seconds=60, now=1.0) is True
