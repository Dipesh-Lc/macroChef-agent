"""Proves POST /feedback derives identity solely from the verified session
token, never from a client-supplied `user_id` -- closing the same bug class
already fixed for app.api.routes_library (commit 58053d3) and
app.api.routes_recommendations (see tests/test_recommendation_isolation.py).
This route was the third instance: `post_feedback` took no session
dependency at all, and `FeedbackRequest.user_id` flowed untrusted into
`FeedbackRepository.add_feedback` / `get_liked_recipe_ids` /
`get_disliked_recipe_ids` -- which `nutrition_scoring_node`'s
`get_user_memory` call keys personalization on.

Covers:
- the wire contract has no `user_id` field at all (schema-level);
- a body-supplied `user_id` is ignored -- the repository call site only ever
  sees the verified session id (spy-based);
- user A's feedback never lands in user B's liked/disliked set (proven via
  the real HTTP route plus a direct repository read);
- no session token -> 401.

Uses an isolated in-memory SQLite database (never the developer's real
macrochef.db) for every test that touches persistence, matching the pattern
in tests/test_recommendation_isolation.py and tests/test_rate_limiting.py.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.dependencies as dependencies_module
import app.services.memory_service as memory_service_module
from app.config import get_settings
from app.data.db import Base
from app.data.repositories import FeedbackRepository
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.schemas.recommendation import FeedbackRequest


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    """Explicit SESSION_SECRET so this suite never depends on ambient
    config -- see the identical fixture pattern in
    tests/test_recommendation_isolation.py and tests/test_rate_limiting.py.
    `_resolve_session_secret` now RAISES when SESSION_SECRET is unset, and
    CI has no `.env`."""
    monkeypatch.setenv("SESSION_SECRET", "feedback-isolation-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def isolated_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Point every session POST /feedback touches at a fresh in-memory
    SQLite DB instead of the developer's real macrochef.db -- mirrors
    tests/test_recommendation_isolation.py's fixture of the same name.

    `app.dependencies.get_session_user`'s sibling `get_db_session` builds its
    session from the `SessionLocal` name bound into `app.dependencies` (via
    `from app.data.db import SessionLocal`), so that's the binding to patch
    -- not `app.data.db.SessionLocal` itself, which `get_db_session` never
    reads directly.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(dependencies_module, "SessionLocal", test_session_local)
    # save_feedback() calls init_db() unconditionally, which would otherwise
    # create tables against the real global engine (app.data.db.engine) --
    # Base.metadata.create_all above already created every table this suite
    # needs, so make init_db a no-op rather than let it touch the
    # developer's real database file. Mirrors
    # tests/test_recommendation_isolation.py's identical fixture.
    monkeypatch.setattr(memory_service_module, "init_db", lambda: None)
    return test_session_local


def _client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _auth_headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _feedback_payload(extra: dict | None = None) -> dict:
    payload = {
        "recipe_id": "secret_recipe",
        "feedback_type": "liked",
        "notes": "test",
    }
    if extra:
        payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# The wire contract has no user_id field at all.
# ---------------------------------------------------------------------------


def test_feedback_request_schema_has_no_user_id_field() -> None:
    assert "user_id" not in FeedbackRequest.model_fields


# ---------------------------------------------------------------------------
# A body-supplied user_id is ignored: identity comes only from the verified
# session token, proven by spying on FeedbackRepository.add_feedback.
# ---------------------------------------------------------------------------


def test_body_supplied_user_id_is_ignored_identity_comes_from_session(
    isolated_session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_user_ids: list[str] = []

    original_add_feedback = FeedbackRepository.add_feedback

    def _spy_add_feedback(self, user_id, request):
        captured_user_ids.append(user_id)
        return original_add_feedback(self, user_id, request)

    monkeypatch.setattr(FeedbackRepository, "add_feedback", _spy_add_feedback)

    client = _client()
    payload = _feedback_payload({"user_id": "attacker_supplied_id"})

    response = client.post(
        "/feedback", json=payload, headers=_auth_headers("real_session_user")
    )

    assert response.status_code == 200
    assert captured_user_ids == ["real_session_user"]


# ---------------------------------------------------------------------------
# User A's feedback never lands in user B's liked/disliked set.
# ---------------------------------------------------------------------------


def test_user_a_feedback_never_lands_in_user_bs_liked_set(
    isolated_session_factory,
) -> None:
    client = _client()

    alice_response = client.post(
        "/feedback",
        json=_feedback_payload({"recipe_id": "alices_recipe", "feedback_type": "liked"}),
        headers=_auth_headers("user_alice"),
    )
    bob_response = client.post(
        "/feedback",
        json=_feedback_payload({"recipe_id": "bobs_recipe", "feedback_type": "disliked"}),
        headers=_auth_headers("user_bob"),
    )

    assert alice_response.status_code == 200
    assert bob_response.status_code == 200

    session = isolated_session_factory()
    try:
        repo = FeedbackRepository(session)
        alice_liked = repo.get_liked_recipe_ids("user_alice")
        bob_liked = repo.get_liked_recipe_ids("user_bob")
        alice_disliked = repo.get_disliked_recipe_ids("user_alice")
        bob_disliked = repo.get_disliked_recipe_ids("user_bob")
    finally:
        session.close()

    assert alice_liked == {"alices_recipe"}
    assert "alices_recipe" not in bob_liked
    assert bob_disliked == {"bobs_recipe"}
    assert "bobs_recipe" not in alice_disliked
    assert "bobs_recipe" not in alice_liked


# ---------------------------------------------------------------------------
# No session token at all -> 401, never a silent anonymous fallback.
# ---------------------------------------------------------------------------


def test_missing_session_token_is_rejected_401(isolated_session_factory) -> None:
    client = _client()
    response = client.post("/feedback", json=_feedback_payload())
    assert response.status_code == 401
