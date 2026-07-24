"""HTTP-level tests for roadmap item "Shareable plan URLs" (Phase 4 item 4):

- POST /share requires a verified session token (401 without one).
- GET /share/{id} requires NO session token at all (the whole point of a
  public share link).
- GET /share/{id} never returns `owner_user_id`, even when the underlying
  DB row has it set.
- 404 is identical for a missing id and a revoked (`is_active=False`) one
  -- no oracle for "exists but was revoked" vs "never existed".
- `disclaimer` is present on every successful GET and equals
  `app.services.share_service.SHARE_DISCLAIMER` exactly.
- IP-keyed rate limiting on GET, session-keyed rate limiting on POST.

Uses an isolated in-memory SQLite database (never the developer's real
macrochef.db), mirroring tests/test_recipe_library_isolation.py and
tests/test_rate_limiting.py.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.data.share_repository as share_repo_module
from app.config import get_settings
from app.data.db import Base
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.services.rate_limiter import get_rate_limiter
from app.services.share_service import SHARE_DISCLAIMER


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "share-routes-test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_share_db(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(share_repo_module, "SessionLocal", test_session_local)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _set_env_limit(monkeypatch: pytest.MonkeyPatch, var: str, value: int | float) -> None:
    monkeypatch.setenv(var, str(value))
    get_settings.cache_clear()


def _recipe_payload(recipe_id: str = "share_route_recipe_1") -> dict:
    return {
        "plan_type": "recipe",
        "recipe": {
            "recipe_id": recipe_id,
            "title": "Shared Recipe",
            "ingredients": [{"name": "rice", "amount": 100, "unit": "g"}],
            "instructions": ["Cook the rice."],
            "owner_user_id": "should-be-stripped-owner",
            "is_user_saved": True,
        },
    }


def _shopping_list_payload() -> dict:
    return {
        "plan_type": "shopping_list",
        "shopping_list": [
            {"name": "flour", "quantity": "short 300 g", "amount": 300, "unit": "g", "reason": None},
            {"name": "eggs", "quantity": "short 2", "amount": 2, "unit": "count", "reason": None},
        ],
    }


# ---------------------------------------------------------------------------
# Auth: POST requires a session, GET does not.
# ---------------------------------------------------------------------------


def test_create_share_without_session_token_is_rejected_401(client: TestClient) -> None:
    response = client.post("/share", json=_recipe_payload())
    assert response.status_code == 401


def test_create_share_with_session_token_succeeds(client: TestClient) -> None:
    response = client.post("/share", json=_recipe_payload(), headers=_headers("owner_user"))
    assert response.status_code == 200
    body = response.json()
    assert "share_id" in body
    assert isinstance(body["share_id"], str) and body["share_id"]


def test_get_share_succeeds_with_no_session_token_at_all(client: TestClient) -> None:
    create_response = client.post(
        "/share", json=_recipe_payload(), headers=_headers("owner_user")
    )
    share_id = create_response.json()["share_id"]

    # Deliberately NO session header on this call.
    response = client.get(f"/share/{share_id}")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Owner id never leaks; the sharer's owner_user_id in the DB row must never
# reach the anonymous GET response.
# ---------------------------------------------------------------------------


def test_get_share_never_returns_owner_user_id_even_though_the_row_has_one(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/share", json=_recipe_payload(), headers=_headers("real_owner_identity_42")
    )
    share_id = create_response.json()["share_id"]

    response = client.get(f"/share/{share_id}")
    assert response.status_code == 200
    body = response.json()

    assert "owner_user_id" not in body
    assert "owner_user_id" not in body.get("content", {})
    assert "real_owner_identity_42" not in response.text
    # The client-supplied sentinel owner_user_id in the request body must
    # also never survive (the server never trusts a client-supplied
    # owner_user_id at all -- it's ignored in favor of the verified session).
    assert "should-be-stripped-owner" not in response.text


# ---------------------------------------------------------------------------
# 404 semantics: missing vs revoked must be indistinguishable.
# ---------------------------------------------------------------------------


def test_get_share_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get("/share/this-id-was-never-created")
    assert response.status_code == 404


def test_get_share_revoked_id_returns_404_same_as_unknown(client: TestClient) -> None:
    from app.data.models import SharedPlan

    create_response = client.post(
        "/share", json=_recipe_payload(), headers=_headers("owner_user")
    )
    share_id = create_response.json()["share_id"]

    # Directly flip is_active off in the DB (simulating a future revoke
    # endpoint -- v1 ships no revoke UI, see docs/BACKLOG.md).
    session = share_repo_module.SessionLocal()
    try:
        row = session.get(SharedPlan, share_id)
        row.is_active = False
        session.commit()
    finally:
        session.close()

    known_missing = client.get("/share/this-id-was-never-created")
    revoked = client.get(f"/share/{share_id}")

    assert known_missing.status_code == 404
    assert revoked.status_code == 404
    assert known_missing.json() == revoked.json()


# ---------------------------------------------------------------------------
# shopping_list plan_type (task: "Shareable Shopping Lists").
# ---------------------------------------------------------------------------


def test_create_share_with_shopping_list_succeeds(client: TestClient) -> None:
    response = client.post(
        "/share", json=_shopping_list_payload(), headers=_headers("owner_user")
    )
    assert response.status_code == 200
    body = response.json()
    assert "share_id" in body
    assert isinstance(body["share_id"], str) and body["share_id"]


def test_get_share_returns_shopping_list_content_unauthenticated(client: TestClient) -> None:
    create_response = client.post(
        "/share", json=_shopping_list_payload(), headers=_headers("owner_user")
    )
    share_id = create_response.json()["share_id"]

    # Deliberately NO session header on this call.
    response = client.get(f"/share/{share_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["plan_type"] == "shopping_list"
    assert body["content"] == [
        {"name": "flour", "quantity": "short 300 g", "amount": 300.0, "unit": "g", "reason": None},
        {"name": "eggs", "quantity": "short 2", "amount": 2.0, "unit": "count", "reason": None},
    ]
    assert body["disclaimer"] == SHARE_DISCLAIMER


def test_create_share_shopping_list_rejects_mismatched_payload(client: TestClient) -> None:
    payload = _shopping_list_payload()
    payload["day_plan"] = {"items": [], "meals_planned": 0}
    response = client.post("/share", json=payload, headers=_headers("owner_user"))
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Disclaimer.
# ---------------------------------------------------------------------------


def test_disclaimer_present_and_matches_the_constant_exactly(client: TestClient) -> None:
    create_response = client.post(
        "/share", json=_recipe_payload(), headers=_headers("owner_user")
    )
    share_id = create_response.json()["share_id"]

    response = client.get(f"/share/{share_id}")
    assert response.status_code == 200
    assert response.json()["disclaimer"] == SHARE_DISCLAIMER


# ---------------------------------------------------------------------------
# Rate limiting.
# ---------------------------------------------------------------------------


def test_create_share_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_SHARE_CREATE_MAX", 2)
    _set_env_limit(monkeypatch, "RATE_LIMIT_SHARE_CREATE_WINDOW_SECONDS", 3600)
    headers = _headers("rl_share_create_user")

    first = client.post("/share", json=_recipe_payload("r1"), headers=headers)
    second = client.post("/share", json=_recipe_payload("r2"), headers=headers)
    third = client.post("/share", json=_recipe_payload("r3"), headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_create_share_rate_limit_is_per_session_not_shared_across_users(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_SHARE_CREATE_MAX", 1)
    _set_env_limit(monkeypatch, "RATE_LIMIT_SHARE_CREATE_WINDOW_SECONDS", 3600)

    user_a_first = client.post(
        "/share", json=_recipe_payload("a1"), headers=_headers("share_user_a")
    )
    user_a_second = client.post(
        "/share", json=_recipe_payload("a2"), headers=_headers("share_user_a")
    )
    user_b_first = client.post(
        "/share", json=_recipe_payload("b1"), headers=_headers("share_user_b")
    )

    assert user_a_first.status_code == 200
    assert user_a_second.status_code == 429
    assert user_b_first.status_code == 200


def test_get_share_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env_limit(monkeypatch, "RATE_LIMIT_SHARE_VIEW_MAX", 2)
    _set_env_limit(monkeypatch, "RATE_LIMIT_SHARE_VIEW_WINDOW_SECONDS", 3600)

    create_response = client.post(
        "/share", json=_recipe_payload(), headers=_headers("owner_user")
    )
    share_id = create_response.json()["share_id"]

    first = client.get(f"/share/{share_id}")
    second = client.get(f"/share/{share_id}")
    third = client.get(f"/share/{share_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
