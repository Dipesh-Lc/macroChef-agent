"""ROADMAP.md Phase 1, Step 1.2 -- LLM call ledger (tokens, cost, latency,
provider).

Covers:
- real usage-metadata extraction for OpenAI (Responses API shape) and
  Anthropic (raw JSON shape) provider responses;
- the len//4 fallback estimate when a provider response carries no usage
  metadata (Ollama fixture below deliberately omits it);
- purpose tags flowing through from each known call site
  (generate_detailed_instructions_with_provider_chain -> "detailed_
  instructions", RecipeGenerationService.generate -> "recipe_generation",
  extract_inventory_with_provider_chain -> "vision_extract"), including
  their mock-provider short-circuit branches (ledger coverage must be
  complete even with no real provider configured);
- fallback_used flagging when the provider used isn't the configured
  primary;
- GET /admin/llm-usage: requires a session, aggregates correctly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.observability.llm_ledger as llm_ledger_module
from app.config import Settings
from app.data.db import Base
from app.data.models import LLMCall
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.observability.llm_ledger import (
    build_usage_response,
    estimate_tokens,
    record_llm_call,
)
from app.schemas.library import RecipeDiscoveryRequest
from app.services import model_provider
from app.services.model_provider import (
    _generate_text,
    extract_inventory_with_provider_chain,
    generate_detailed_instructions_with_provider_chain,
)
from app.services.recipe_generation_service import RecipeGenerationService


@pytest.fixture()
def isolated_ledger_db(monkeypatch: pytest.MonkeyPatch):
    """Point the LLM ledger at a fresh in-memory SQLite DB instead of the
    developer's real macrochef.db -- mirrors the isolated-DB fixture
    pattern used throughout this test suite (e.g.
    tests/test_feedback_isolation.py, tests/test_observability_events.py)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(llm_ledger_module, "SessionLocal", test_session_local)
    return test_session_local


def _all_calls(session_factory) -> list[LLMCall]:
    session = session_factory()
    try:
        return list(session.scalars(select(LLMCall)).all())
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Real usage-metadata extraction: OpenAI (Responses API) and Anthropic (raw
# JSON via requests.post).
# ---------------------------------------------------------------------------


def test_openai_usage_extraction(isolated_ledger_db, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(MODEL_PROVIDER="openai", OPENAI_API_KEY="test-key")

    fake_response = SimpleNamespace(
        output_text="Here are your steps.",
        usage=SimpleNamespace(input_tokens=123, output_tokens=45, total_tokens=168),
    )

    class _FakeResponses:
        def create(self, **kwargs):
            return fake_response

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = _FakeResponses()

    fake_openai_module = SimpleNamespace(OpenAI=_FakeOpenAI)
    monkeypatch.setitem(__import__("sys").modules, "openai", fake_openai_module)

    text = _generate_text("openai", "a prompt", settings, purpose="test_openai")
    assert text == "Here are your steps."

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "openai"
    assert row.purpose == "test_openai"
    assert row.prompt_tokens == 123
    assert row.completion_tokens == 45
    assert row.success is True
    # gpt-4.1-mini is the default openai chat model (app.services.
    # model_provider.DEFAULT_MODELS) and IS priced in PRICE_PER_MTOK, so
    # cost must be computed from real usage, not left at $0.
    assert row.model == "gpt-4.1-mini"
    assert row.cost_usd > 0


def test_anthropic_usage_extraction(isolated_ledger_db, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(MODEL_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key")

    fake_json = {
        "content": [{"type": "text", "text": "Here are your steps."}],
        "usage": {"input_tokens": 88, "output_tokens": 21},
    }

    def _fake_post(url, headers=None, json=None, timeout=None):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: fake_json)

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    text = _generate_text("anthropic", "a prompt", settings, purpose="test_anthropic")
    assert text == "Here are your steps."

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "anthropic"
    assert row.prompt_tokens == 88
    assert row.completion_tokens == 21
    assert row.model == "claude-sonnet-4-5"
    assert row.cost_usd > 0


def test_fallback_token_estimate_kicks_in_when_usage_metadata_absent(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama's /api/chat response carries no token-usage fields in this
    fixture -- record_llm_call must fall back to `estimate_tokens` (~4
    chars/token) rather than leaving the counts as None/missing."""
    settings = Settings(MODEL_PROVIDER="ollama")
    prompt = "a" * 40  # -> 10 estimated tokens
    completion = "b" * 20  # -> 5 estimated tokens

    def _fake_post(url, headers=None, json=None, timeout=None):
        # Deliberately no prompt_eval_count/eval_count keys.
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": completion}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    text = _generate_text("ollama", prompt, settings, purpose="test_estimate")
    assert text == completion

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    row = rows[0]
    assert row.prompt_tokens == estimate_tokens(prompt) == 10
    assert row.completion_tokens == estimate_tokens(completion) == 5
    # ollama is always free regardless of real/estimated token counts.
    assert row.cost_usd == 0.0


def test_estimate_tokens_is_roughly_four_chars_per_token() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2


# ---------------------------------------------------------------------------
# Purpose tags flow through from each known call site, including their
# mock-provider short-circuit branches.
# ---------------------------------------------------------------------------


def test_detailed_instructions_mock_path_records_ledger_row(isolated_ledger_db) -> None:
    steps, generated = generate_detailed_instructions_with_provider_chain(
        title="Toast",
        ingredients=["bread"],
        instructions=["Toast it."],
    )
    assert generated is False
    assert steps == ["Toast it."]

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].provider == "mock"
    assert rows[0].purpose == "detailed_instructions"
    assert rows[0].prompt_tokens == 0
    assert rows[0].completion_tokens == 0
    assert rows[0].cost_usd == 0.0
    assert rows[0].success is True


def test_recipe_generation_mock_path_records_ledger_row(isolated_ledger_db) -> None:
    request = RecipeDiscoveryRequest(count=1)
    candidates = RecipeGenerationService().generate(request)
    assert candidates == []

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].provider == "mock"
    assert rows[0].purpose == "recipe_generation"


def test_vision_extract_mock_path_records_ledger_row(isolated_ledger_db) -> None:
    def _mock_extractor(image_path):
        return []

    extract_inventory_with_provider_chain(None, _mock_extractor)

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].provider == "mock"
    assert rows[0].purpose == "vision_extract"


def test_fallback_used_flags_a_non_primary_provider(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """settings.model_provider is "openai" but this call is routed to
    "anthropic" directly -- fallback_used must be True (see
    model_provider._is_fallback_provider)."""
    settings = Settings(MODEL_PROVIDER="openai")

    def _fake_post(url, headers=None, json=None, timeout=None):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"content": [{"type": "text", "text": "hi"}], "usage": {}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    _generate_text("anthropic", "prompt", settings, purpose="test_fallback")

    rows = _all_calls(isolated_ledger_db)
    assert rows[0].fallback_used is True


def test_record_llm_call_prefers_real_counts_over_estimate(isolated_ledger_db) -> None:
    """A provided real count is never overridden by the len//4 estimate,
    even when prompt_text/completion_text would estimate differently."""
    record_llm_call(
        provider="openai",
        model="gpt-4.1-mini",
        purpose="direct_test",
        prompt_tokens=5,
        completion_tokens=7,
        latency_ms=1.0,
        success=True,
        fallback_used=False,
        prompt_text="a" * 400,  # would estimate to 100 if used
        completion_text="b" * 400,
    )
    rows = _all_calls(isolated_ledger_db)
    assert rows[0].prompt_tokens == 5
    assert rows[0].completion_tokens == 7


# ---------------------------------------------------------------------------
# GET /admin/llm-usage
# ---------------------------------------------------------------------------


@pytest.fixture()
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings

    monkeypatch.setenv("SESSION_SECRET", "llm-ledger-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_admin_llm_usage_requires_a_session(isolated_ledger_db, _session_secret) -> None:
    client = TestClient(create_app())
    response = client.get("/admin/llm-usage")
    assert response.status_code == 401


def test_admin_llm_usage_aggregates_calls_tokens_and_cost(
    isolated_ledger_db, _session_secret
) -> None:
    record_llm_call(
        provider="openai",
        model="gpt-4.1-mini",
        purpose="recipe_generation",
        prompt_tokens=1_000_000,
        completion_tokens=0,
        latency_ms=10.0,
        success=True,
        fallback_used=False,
    )
    record_llm_call(
        provider="openai",
        model="gpt-4.1-mini",
        purpose="recipe_generation",
        prompt_tokens=1_000_000,
        completion_tokens=0,
        latency_ms=12.0,
        success=False,
        fallback_used=True,
    )
    record_llm_call(
        provider="mock",
        model="mock",
        purpose="detailed_instructions",
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0.0,
        success=True,
        fallback_used=False,
    )

    response = build_usage_response(days=7)

    assert response.totals.calls == 3
    assert response.totals.prompt_tokens == 2_000_000
    # $0.40/MTok prompt price for gpt-4.1-mini * 2 calls of 1M prompt tokens.
    assert response.totals.cost_usd == pytest.approx(0.80)

    generation_row = next(
        row
        for row in response.rows
        if row.purpose == "recipe_generation" and row.provider == "openai"
    )
    assert generation_row.calls == 2
    assert generation_row.success_count == 1
    assert generation_row.failure_count == 1
    assert generation_row.fallback_count == 1
    assert generation_row.cost_usd == pytest.approx(0.80)

    mock_row = next(row for row in response.rows if row.provider == "mock")
    assert mock_row.calls == 1
    assert mock_row.cost_usd == 0.0


def test_admin_llm_usage_http_endpoint_returns_aggregates(
    isolated_ledger_db, _session_secret
) -> None:
    record_llm_call(
        provider="gemini",
        model="gemini-2.5-flash",
        purpose="vision_extract",
        prompt_tokens=500,
        completion_tokens=200,
        latency_ms=5.0,
        success=True,
        fallback_used=False,
    )

    client = TestClient(create_app())
    token = mint_session_token("ledger_admin_test_user")
    response = client.get("/admin/llm-usage?days=7", headers={SESSION_TOKEN_HEADER: token})

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["calls"] == 1
    assert body["rows"][0]["purpose"] == "vision_extract"
    assert body["rows"][0]["provider"] == "gemini"
