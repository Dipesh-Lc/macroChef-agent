from app.config import Settings
from app.services.model_provider import (
    _build_detailed_instructions_prompt,
    _models_for,
    _parse_numbered_steps,
    generate_detailed_instructions_with_provider_chain,
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
