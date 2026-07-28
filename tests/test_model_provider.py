import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.observability.llm_ledger as llm_ledger_module
from app.config import Settings
from app.data.db import Base
from app.data.models import LLMCall
from app.services import model_provider
from app.services.model_provider import (
    DetailedInstructions,
    StructuredGenerationError,
    _build_detailed_instructions_prompt,
    _detailed_instructions_text_fallback,
    _models_for,
    _parse_numbered_steps,
    generate_detailed_instructions_with_provider_chain,
    generate_structured,
    provider_chain,
)


def test_provider_chain_uses_default_then_configured_fallbacks() -> None:
    settings = Settings(MODEL_PROVIDER="gemini", MODEL_PROVIDER_FALLBACKS="openai,claude,local")

    assert provider_chain(settings) == ["gemini", "openai", "anthropic", "ollama", "mock"]


def test_provider_chain_deduplicates_and_keeps_mock_available() -> None:
    settings = Settings(MODEL_PROVIDER="openai", MODEL_PROVIDER_FALLBACKS="openai,mock")

    assert provider_chain(settings) == ["openai", "mock"]


def test_gemini_31_preview_settings_are_configurable() -> None:
    settings = Settings(
        MODEL_PROVIDER="google",
        GEMINI_CHAT_MODEL="gemini-3.1-flash-lite-preview",
        GEMINI_VISION_MODEL="gemini-3.1-flash-lite-preview",
        GEMINI_CHAT_MODEL_FALLBACKS="gemini-2.5-flash",
        GEMINI_VISION_MODEL_FALLBACKS="gemini-2.5-flash",
        GEMINI_API_VERSION="v1beta",
        GEMINI_THINKING_LEVEL="low",
    )

    assert provider_chain(settings)[0] == "gemini"
    assert settings.gemini_chat_model == "gemini-3.1-flash-lite-preview"
    assert settings.gemini_vision_model == "gemini-3.1-flash-lite-preview"
    assert _models_for(settings, "gemini", "chat") == [
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash",
    ]
    assert _models_for(settings, "gemini", "vision") == [
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash",
    ]
    assert settings.gemini_api_version == "v1beta"
    assert settings.gemini_thinking_level == "low"


# ---------------------------------------------------------------------------
# generate_detailed_instructions_with_provider_chain + its prompt/parser
# helpers -- "Get detailed instructions" feature.
# ---------------------------------------------------------------------------


def test_build_detailed_instructions_prompt_includes_guardrails_and_content() -> None:
    prompt = _build_detailed_instructions_prompt(
        title="Simple Fried Rice",
        ingredients=["2 cups cooked rice", "1 tbsp soy sauce"],
        instructions=["Cook the eggs.", "Stir-fry everything together."],
        servings=2,
        cuisine="Chinese",
    )

    assert "Simple Fried Rice" in prompt
    assert "2 cups cooked rice" in prompt
    assert "Cook the eggs." in prompt
    assert "Do NOT add, remove, or" in prompt
    assert "substitute any ingredient" in prompt
    assert "Do NOT state or imply anything about calories, nutrition" in prompt
    assert "allergy/diet" in prompt
    assert "cuisine: Chinese" in prompt
    assert "servings: 2" in prompt


def test_build_detailed_instructions_prompt_handles_missing_optional_fields() -> None:
    prompt = _build_detailed_instructions_prompt(
        title="Toast",
        ingredients=[],
        instructions=[],
        servings=None,
        cuisine=None,
    )

    assert "Toast" in prompt
    assert "none given" in prompt


def test_parse_numbered_steps_strips_markers_and_drops_blank_lines() -> None:
    text = """
    1. Preheat the oven to 400F.
    2) Season the chicken with salt and pepper.

    3 - Roast for 25 minutes until golden.
    """

    steps = _parse_numbered_steps(text)

    assert steps == [
        "Preheat the oven to 400F.",
        "Season the chicken with salt and pepper.",
        "Roast for 25 minutes until golden.",
    ]


def test_parse_numbered_steps_falls_back_to_raw_line_without_a_marker() -> None:
    text = "Just one unmarked step."

    steps = _parse_numbered_steps(text)

    assert steps == ["Just one unmarked step."]


def test_parse_numbered_steps_returns_empty_list_for_blank_text() -> None:
    assert _parse_numbered_steps("   \n\n  ") == []


def test_mock_provider_echoes_original_instructions_unchanged() -> None:
    original = ["Cook the eggs.", "Stir-fry the rice."]

    steps, generated = generate_detailed_instructions_with_provider_chain(
        title="Simple Fried Rice",
        ingredients=["2 cups cooked rice", "2 eggs"],
        instructions=original,
        servings=2,
        cuisine="Chinese",
    )

    assert steps == original
    assert steps is not original  # a defensive copy, never the same list object
    assert generated is False


# ---------------------------------------------------------------------------
# generate_structured (ROADMAP.md Phase 2, Step 2.1) -- native schema passed
# per provider, the one-shot "repair loop", and parse_fallback flagging for
# Ollama/mock.
# ---------------------------------------------------------------------------


class _SampleStructured(BaseModel):
    """A minimal schema for exercising `generate_structured` directly,
    independent of any of this module's real production schemas."""

    name: str
    count: int = 0


@pytest.fixture()
def isolated_ledger_db(monkeypatch: pytest.MonkeyPatch):
    """Point the LLM ledger at a fresh in-memory SQLite DB -- mirrors the
    fixture of the same name in tests/test_llm_ledger.py."""
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


def test_generate_structured_gemini_passes_response_schema(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(MODEL_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    captured: dict = {}

    fake_response = SimpleNamespace(
        text='{"name": "a", "count": 3}',
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=5),
    )

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["config"] = config
            return fake_response

    class _FakeClient:
        def __init__(self):
            self.models = _FakeModels()

    monkeypatch.setattr(model_provider, "_gemini_client", lambda settings: _FakeClient())

    result = generate_structured(
        "gemini", "a prompt", _SampleStructured, settings, purpose="test_gemini_structured"
    )

    assert result == _SampleStructured(name="a", count=3)
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_schema == _SampleStructured.model_json_schema()

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].parse_fallback is False
    assert rows[0].retries == 0
    assert rows[0].prompt_tokens == 10
    assert rows[0].completion_tokens == 5


def test_generate_structured_openai_passes_json_schema(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(MODEL_PROVIDER="openai", OPENAI_API_KEY="test-key")
    captured: dict = {}

    fake_response = SimpleNamespace(
        output_text='{"name": "a", "count": 3}',
        usage=SimpleNamespace(input_tokens=12, output_tokens=6),
    )

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return fake_response

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = generate_structured(
        "openai", "a prompt", _SampleStructured, settings, purpose="test_openai_structured"
    )

    assert result == _SampleStructured(name="a", count=3)
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["schema"] == _SampleStructured.model_json_schema()
    assert captured["text"]["format"]["strict"] is False

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].parse_fallback is False
    assert rows[0].prompt_tokens == 12
    assert rows[0].completion_tokens == 6


def test_generate_structured_anthropic_uses_forced_tool_use(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(MODEL_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key")
    captured: dict = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        payload = json
        captured.update(payload)
        tool_name = payload["tools"][0]["name"]
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "content": [
                    {"type": "tool_use", "name": tool_name, "input": {"name": "a", "count": 3}}
                ],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    result = generate_structured(
        "anthropic", "a prompt", _SampleStructured, settings, purpose="test_anthropic_structured"
    )

    assert result == _SampleStructured(name="a", count=3)
    assert captured["tools"][0]["input_schema"] == _SampleStructured.model_json_schema()
    assert captured["tool_choice"] == {"type": "tool", "name": captured["tools"][0]["name"]}
    assert captured["max_tokens"] == model_provider.ANTHROPIC_STRUCTURED_MAX_TOKENS

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].parse_fallback is False
    assert rows[0].prompt_tokens == 20
    assert rows[0].completion_tokens == 10


def test_generate_structured_repair_loop_retries_once_then_succeeds(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed-response unit test exercising the repair loop end-to-end
    (ROADMAP 2.1 acceptance criterion): the first Ollama response is
    unparseable JSON, the second (after the repair-loop retry appends the
    validation errors to the prompt) is valid."""
    settings = Settings(MODEL_PROVIDER="ollama")
    call_count = {"n": 0}

    def _fake_post(url, headers=None, json=None, timeout=None):
        call_count["n"] += 1
        content = '{"name": "a"' if call_count["n"] == 1 else '{"name": "a", "count": 3}'
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": content}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    result = generate_structured(
        "ollama", "a prompt", _SampleStructured, settings, purpose="test_repair_loop"
    )

    assert result == _SampleStructured(name="a", count=3)
    assert call_count["n"] == 2

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].retries == 1
    assert rows[0].success is True
    assert rows[0].parse_fallback is True


def test_generate_structured_raises_after_repair_retry_also_fails(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(MODEL_PROVIDER="ollama")

    def _fake_post(url, headers=None, json=None, timeout=None):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "not json at all"}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    with pytest.raises(StructuredGenerationError):
        generate_structured(
            "ollama", "a prompt", _SampleStructured, settings, purpose="test_repair_loop_fails"
        )

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].retries == 1
    assert rows[0].success is False
    assert rows[0].parse_fallback is True


def test_generate_structured_mock_provider_flags_parse_fallback(isolated_ledger_db) -> None:
    """mock legitimately shows parse_fallback=True -- it's the fallback
    path by design (ROADMAP 2.1 acceptance criterion)."""
    settings = Settings(MODEL_PROVIDER="mock")

    result = generate_structured(
        "mock", "a prompt", _SampleStructured, settings, purpose="test_mock_structured"
    )

    assert result == _SampleStructured(name="mock", count=0)

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].provider == "mock"
    assert rows[0].parse_fallback is True
    assert rows[0].retries == 0
    assert rows[0].success is True


def test_generate_structured_text_fallback_recovers_non_json_response(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller-supplied `text_fallback` hook recovers a response that
    isn't JSON at all (e.g. a small local model ignoring the JSON-mode
    instruction), on the FIRST attempt -- no repair-loop retry needed."""
    settings = Settings(MODEL_PROVIDER="ollama")

    def _fake_post(url, headers=None, json=None, timeout=None):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "1. Preheat oven.\n2. Roast for 20 minutes."}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)

    result = generate_structured(
        "ollama",
        "a prompt",
        DetailedInstructions,
        settings,
        purpose="test_text_fallback",
        text_fallback=_detailed_instructions_text_fallback,
    )

    assert result.steps == ["Preheat oven.", "Roast for 20 minutes."]

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].retries == 0
    assert rows[0].parse_fallback is True


def test_detailed_instructions_recovers_ollama_numbered_list_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same scenario as the test above, but through the full public entry
    point (`generate_detailed_instructions_with_provider_chain`), proving
    the `text_fallback` wiring is correct end-to-end, not just when called
    directly."""
    settings = Settings(MODEL_PROVIDER="ollama")

    def _fake_post(url, headers=None, json=None, timeout=None):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "1. Do the thing."}},
        )

    monkeypatch.setattr(model_provider.requests, "post", _fake_post)
    monkeypatch.setattr(model_provider, "get_settings", lambda: settings)

    steps, generated = generate_detailed_instructions_with_provider_chain(
        title="Toast", ingredients=["bread"], instructions=["Toast it."]
    )

    assert generated is True
    assert steps == ["Do the thing."]


def test_recipe_generation_service_routes_through_generate_structured(
    isolated_ledger_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a non-mock provider's structured JSON response comes
    back as real `RecipeCandidate` objects via `generate_structured` +
    the existing `_sanitize_candidate_payload` pipeline -- including a
    candidate that OMITS `candidate_id` (regression coverage for the
    `_RecipeCandidatePayload.model_dump()` always including the key as
    `None`, which `.setdefault()` would silently fail to backfill)."""
    from app.schemas.library import RecipeDiscoveryRequest
    from app.services.recipe_generation_service import RecipeGenerationService

    settings_holder = Settings(MODEL_PROVIDER="openai", OPENAI_API_KEY="test-key")
    fake_response = SimpleNamespace(
        output_text=(
            '{"candidates": [{"title": "Chicken Rice Bowl", '
            '"ingredients": ["150 g chicken breast", "120 g cooked rice"], '
            '"instructions": ["Cook rice.", "Sear chicken."], "servings": 2}]}'
        ),
        usage=SimpleNamespace(input_tokens=30, output_tokens=15),
    )

    class _FakeResponses:
        def create(self, **kwargs):
            return fake_response

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setattr(
        "app.services.recipe_generation_service.get_settings", lambda: settings_holder
    )

    candidates = RecipeGenerationService().generate(RecipeDiscoveryRequest(count=1))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Chicken Rice Bowl"
    assert candidate.candidate_id  # backfilled, never left None/empty
    assert candidate.ingredients[0].name == "chicken breast"
    assert candidate.ingredients[0].amount == 150
    assert candidate.source_type == "ai_generated"

    rows = _all_calls(isolated_ledger_db)
    assert len(rows) == 1
    assert rows[0].purpose == "recipe_generation"
    assert rows[0].parse_fallback is False
