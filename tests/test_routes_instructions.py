"""HTTP-level tests for POST /recipes/instructions -- the "Get detailed
instructions" feature (phrasing/elaboration only, see
app.services.model_provider.generate_detailed_instructions_with_provider_chain
and its docstring for the safety guardrails baked into the prompt).

Covers:
- mock/no-provider mode returns the original instructions unchanged,
  generated=False, and a provider_note;
- session required -- unauthenticated request is rejected 401, same as
  every other session-gated /recipes/* route (see
  tests/test_recommendation_isolation.py's identical assertion for
  /recipes/recommend);
- rate limiting reuses require_recommend_rate_limit, the exact same bucket
  as /recipes/recommend (see tests/test_rate_limiting.py's
  test_recommend_nth_plus_one_request_gets_429 for the precedent this
  mirrors) -- proven both standalone and as a shared bucket with
  /recipes/recommend.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.services.rate_limiter import get_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "instructions-route-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _payload(**overrides) -> dict:
    payload = {
        "title": "Simple Fried Rice",
        "ingredients": ["2 cups cooked rice", "1 tbsp soy sauce", "2 eggs"],
        "instructions": ["Cook the eggs.", "Stir-fry the rice with soy sauce and eggs."],
        "servings": 2,
        "cuisine": "Chinese",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Mock mode: original instructions echoed back unchanged.
# ---------------------------------------------------------------------------


def test_mock_mode_returns_original_instructions_unchanged(client: TestClient) -> None:
    payload = _payload()

    response = client.post(
        "/recipes/instructions", json=payload, headers=_headers("instr_user_1")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["steps"] == payload["instructions"]
    assert body["generated"] is False
    assert body["provider_note"]


def test_mock_mode_never_fabricates_new_step_content(client: TestClient) -> None:
    payload = _payload(instructions=["Preheat the oven."])

    response = client.post(
        "/recipes/instructions", json=payload, headers=_headers("instr_user_2")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["steps"] == ["Preheat the oven."]
    assert body["generated"] is False


# ---------------------------------------------------------------------------
# Session required.
# ---------------------------------------------------------------------------


def test_missing_session_token_is_rejected_401(client: TestClient) -> None:
    response = client.post("/recipes/instructions", json=_payload())

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting -- reuses the /recipes/recommend bucket (require_recommend_rate_limit).
# ---------------------------------------------------------------------------


def test_instructions_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_RECOMMEND_MAX", "2")
    monkeypatch.setenv("RATE_LIMIT_RECOMMEND_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()
    headers = _headers("instr_rl_user")
    payload = _payload()

    first = client.post("/recipes/instructions", json=payload, headers=headers)
    second = client.post("/recipes/instructions", json=payload, headers=headers)
    third = client.post("/recipes/instructions", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    get_settings.cache_clear()


def test_instructions_shares_the_recommend_rate_limit_bucket(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/recipes/instructions and /recipes/recommend key the same verified-
    session bucket (both go through require_recommend_rate_limit) -- calls
    to one count against the other's budget."""
    monkeypatch.setenv("RATE_LIMIT_RECOMMEND_MAX", "2")
    monkeypatch.setenv("RATE_LIMIT_RECOMMEND_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()
    headers = _headers("instr_shared_bucket_user")

    first = client.post("/recipes/instructions", json=_payload(), headers=headers)
    second = client.post(
        "/recipes/recommend",
        json={"user_profile": {}},
        headers=headers,
    )
    third = client.post("/recipes/instructions", json=_payload(), headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    get_settings.cache_clear()
