from app.config import Settings
from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.schemas.recommendation import RecipeScore
from app.services.model_provider import _macro_summary, _models_for, provider_chain, template_explanation


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


def _recipe(**kwargs) -> Recipe:
    defaults = {
        "recipe_id": "r",
        "title": "Test Recipe",
        "ingredients": [],
        "instructions": ["Cook."],
        # A self-reported tag that must never leak into the explanation once
        # `nutrition` exists -- a mismatched value here is the regression guard.
        "calories": 999,
        "protein_g": 999,
        "carbs_g": 999,
        "fat_g": 999,
        "fiber_g": 999,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


def _score() -> RecipeScore:
    return RecipeScore(
        recipe_id="r",
        pantry_match_score=0.8,
        macro_fit_score=0.9,
        time_score=0.7,
        preference_score=0.5,
        final_score=0.75,
        used_ingredients=["chicken breast"],
        missing_ingredients=[],
    )


def test_macro_summary_unknown_when_ungrounded() -> None:
    recipe = _recipe()

    assert _macro_summary(recipe) == "Macros have not been verified for this recipe yet."


def test_macro_summary_reads_computed_not_tag_when_grounded() -> None:
    macros = FoodMacros(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)
    nutrition = RecipeNutrition(status=GroundingStatus.GROUNDED, servings=1, total=macros, per_serving=macros, coverage=1.0)
    recipe = _recipe(nutrition=nutrition)

    summary = _macro_summary(recipe)

    assert "500 calories" in summary
    assert "999" not in summary


def test_macro_summary_flags_partial_as_undercount() -> None:
    macros = FoodMacros(calories=300, protein_g=20, carbs_g=30, fat_g=8, fiber_g=4)
    nutrition = RecipeNutrition(
        status=GroundingStatus.PARTIAL, servings=1, total=macros, per_serving=macros,
        ungrounded_ingredients=["mystery sauce"], coverage=0.5,
    )
    recipe = _recipe(nutrition=nutrition)

    summary = _macro_summary(recipe)

    assert "50%" in summary
    assert "undercount" in summary
    assert "999" not in summary


def test_template_explanation_never_leaks_tag_macros_when_ungrounded() -> None:
    recipe = _recipe()

    explanation = template_explanation(recipe, _score())

    assert "999" not in explanation
    assert "not been verified" in explanation
