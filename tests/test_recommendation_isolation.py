"""Proves /recipes/recommend derives identity solely from the verified
session token, never from a client-supplied `user_id` -- closing the same
bug class app.api.routes_library was already fixed for (see commit
58053d3 and tests/test_recipe_library_isolation.py). This route was missed
by that commit: `RecommendationRequest.user_id` used to default to
"demo_user" and flowed untrusted into `list_user_recipes`,
`get_user_memory`, and `save_session_summary` inside the recommendation
graph.

Covers:
- the wire contract has no `user_id` field at all (schema-level);
- a body-supplied `user_id` is ignored -- the graph's identity-sensitive
  call sites only ever see the verified session id (spy-based);
- user A's saved-library recipe never surfaces in user B's recommendations,
  and does surface in user A's own (end-to-end, via the real HTTP route);
- no session token -> 401.

Uses an isolated in-memory SQLite database (never the developer's real
macrochef.db) for every test that touches persistence, and forces
RecipeRetriever onto its deterministic keyword-search path (bypassing
whatever this developer's real Chroma store happens to have persisted --
irrelevant to, and would otherwise make flaky, the isolation property under
test here).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.graph.nodes as nodes_module
import app.services.memory_service as memory_service_module
import app.services.recipe_retriever as recipe_retriever_module
from app.config import get_settings
from app.data.db import Base
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.schemas.recipe import Recipe
from app.schemas.recommendation import RecommendationRequest


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    """Explicit SESSION_SECRET so this suite never depends on ambient
    config -- see the identical fixture pattern in tests/test_rate_limiting.py
    and tests/test_session_auth.py. `_resolve_session_secret` now RAISES when
    SESSION_SECRET is unset, and CI has no `.env`."""
    monkeypatch.setenv("SESSION_SECRET", "recommendation-isolation-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def isolated_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Point every repository the recommendation graph touches at a fresh
    in-memory SQLite DB instead of the developer's real macrochef.db --
    mirrors tests/test_recipe_library_isolation.py's fixture of the same
    name, extended to also cover app.services.memory_service (get_user_memory
    / save_session_summary), which the /library routes never call but the
    recommendation graph does."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(RecipeLibraryRepository, "_session", lambda self: test_session_local())
    monkeypatch.setattr(memory_service_module, "SessionLocal", test_session_local)
    # init_db() (called by get_user_memory/save_session_summary) creates
    # tables against the real global engine (app.data.db.engine), not our
    # isolated one -- Base.metadata.create_all above already created every
    # table this suite needs, so make init_db a no-op rather than let it
    # touch the developer's real database file.
    monkeypatch.setattr(memory_service_module, "init_db", lambda: None)
    return test_session_local


@pytest.fixture(autouse=True)
def _force_keyword_retrieval(monkeypatch: pytest.MonkeyPatch):
    """Force RecipeRetriever.retrieve onto its deterministic keyword-search
    path. The identity-isolation property under test lives entirely in
    RecipeLibraryRepository.list_user_recipes scoping, not in retrieval
    ranking -- whatever this developer's real, shared vector store happens
    to have persisted from prior corpus imports is an irrelevant (and
    environment-dependent, hence flaky) variable to control out here."""

    class _EmptyVectorStore:
        def count(self) -> int:
            return 0

    monkeypatch.setattr(recipe_retriever_module, "get_vector_store", lambda: _EmptyVectorStore())


def _client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _auth_headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _secret_recipe() -> Recipe:
    # A deliberately nonsense ingredient name/token: it cannot fuzzy-match or
    # collide with any real canonical ingredient
    # (app.utils.ingredient_normalizer.CANONICAL_INGREDIENTS), so its
    # presence in a request's typed_ingredients is an unambiguous, high
    # pantry-match signal for exactly this one recipe.
    return Recipe(
        recipe_id="user_alice_secret_dish",
        title="Alice's Secret Xyzzyplorp Bake",
        ingredients=[{"name": "xyzzyplorp", "amount": 10, "unit": "g"}],
        instructions=["Bake the xyzzyplorp."],
        cook_time_min=15,
    )


def _recommend_payload(extra: dict | None = None) -> dict:
    payload = {
        "input_type": "text",
        "typed_ingredients": "xyzzyplorp",
        "user_profile": {
            "allergies": [],
            "disliked_ingredients": [],
            "diet_type": None,
            "preferred_cuisines": [],
            "macro_targets": {},
            "max_cook_time_min": 60,
        },
    }
    if extra:
        payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# The wire contract has no user_id field at all.
# ---------------------------------------------------------------------------


def test_recommendation_request_schema_has_no_user_id_field() -> None:
    assert "user_id" not in RecommendationRequest.model_fields


# ---------------------------------------------------------------------------
# A body-supplied user_id is ignored: identity comes only from the verified
# session token, proven by spying on the graph's three identity-sensitive
# call sites (list_user_recipes / get_user_memory / save_session_summary).
# ---------------------------------------------------------------------------


def test_body_supplied_user_id_is_ignored_identity_comes_from_session(
    isolated_session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_user_ids: list[str] = []

    original_list_user_recipes = RecipeLibraryRepository.list_user_recipes

    def _spy_list_user_recipes(self, user_id):
        captured_user_ids.append(user_id)
        return original_list_user_recipes(self, user_id)

    monkeypatch.setattr(RecipeLibraryRepository, "list_user_recipes", _spy_list_user_recipes)

    original_get_user_memory = nodes_module.get_user_memory

    def _spy_get_user_memory(user_id, db=None):
        captured_user_ids.append(user_id)
        return original_get_user_memory(user_id, db)

    monkeypatch.setattr(nodes_module, "get_user_memory", _spy_get_user_memory)

    original_save_session_summary = nodes_module.save_session_summary

    def _spy_save_session_summary(user_id, recommendations, db=None):
        captured_user_ids.append(user_id)
        return original_save_session_summary(user_id, recommendations, db)

    monkeypatch.setattr(nodes_module, "save_session_summary", _spy_save_session_summary)

    client = _client()
    payload = _recommend_payload({"user_id": "attacker_supplied_id"})

    response = client.post(
        "/recipes/recommend", json=payload, headers=_auth_headers("real_session_user")
    )

    assert response.status_code == 200
    assert captured_user_ids, "the spied call sites were never exercised"
    assert set(captured_user_ids) == {"real_session_user"}


# ---------------------------------------------------------------------------
# User A's saved-library recipe never surfaces in user B's recommendations.
# ---------------------------------------------------------------------------


def test_user_a_recommendations_never_surface_user_bs_saved_library(
    isolated_session_factory,
) -> None:
    RecipeLibraryRepository().save_recipe("user_alice", _secret_recipe())

    client = _client()
    payload = _recommend_payload()

    alice_response = client.post(
        "/recipes/recommend", json=payload, headers=_auth_headers("user_alice")
    )
    bob_response = client.post(
        "/recipes/recommend", json=payload, headers=_auth_headers("user_bob")
    )

    assert alice_response.status_code == 200
    assert bob_response.status_code == 200

    alice_titles = [item["recipe"]["title"] for item in alice_response.json()["recommendations"]]
    bob_titles = [item["recipe"]["title"] for item in bob_response.json()["recommendations"]]

    assert "Alice's Secret Xyzzyplorp Bake" in alice_titles
    assert "Alice's Secret Xyzzyplorp Bake" not in bob_titles


# ---------------------------------------------------------------------------
# No session token at all -> 401, never a silent anonymous fallback.
# ---------------------------------------------------------------------------


def test_missing_session_token_is_rejected_401(isolated_session_factory) -> None:
    client = _client()
    response = client.post("/recipes/recommend", json=_recommend_payload())
    assert response.status_code == 401
