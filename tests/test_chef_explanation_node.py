import pytest

import app.graph.nodes as nodes_module
from app.graph.nodes import LLM_EXPLANATION_LIMIT, chef_explanation_node
from app.graph.state import MacroChefState
from app.schemas.recipe import Recipe
from app.schemas.recommendation import MealRecommendation, RecipeScore


def _recipe(recipe_id: str) -> Recipe:
    return Recipe(recipe_id=recipe_id, title=f"Recipe {recipe_id}", ingredients=[], instructions=["Cook."])


def _score(recipe_id: str) -> RecipeScore:
    return RecipeScore(
        recipe_id=recipe_id,
        pantry_match_score=0.8,
        macro_fit_score=0.9,
        time_score=0.7,
        preference_score=0.5,
        final_score=0.75,
        used_ingredients=["chicken breast"],
        missing_ingredients=[],
    )


def _recommendation(recipe_id: str) -> MealRecommendation:
    return MealRecommendation(
        recipe=_recipe(recipe_id), score=_score(recipe_id), explanation="", shopping_list=[]
    )


def test_chef_explanation_node_caps_real_llm_calls_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    total_recommendations = LLM_EXPLANATION_LIMIT + 7
    recommendations = [_recommendation(str(index)) for index in range(total_recommendations)]
    state = MacroChefState(final_recommendations=recommendations)

    call_count = 0

    def _fake_explain_recommendation(recipe, score, allergy_safe=True):
        nonlocal call_count
        call_count += 1
        return f"LLM explanation for {recipe.recipe_id}"

    monkeypatch.setattr(nodes_module, "explain_recommendation", _fake_explain_recommendation)

    result = chef_explanation_node(state)
    updated_state = MacroChefState.model_validate(result)

    assert call_count == LLM_EXPLANATION_LIMIT
    assert len(updated_state.final_recommendations) == total_recommendations
    for recommendation in updated_state.final_recommendations:
        assert recommendation.explanation
        assert recommendation.explanation.strip() != ""

    # The first LLM_EXPLANATION_LIMIT recommendations get the real (mocked)
    # LLM explanation; the rest fall back to the deterministic template.
    for recommendation in updated_state.final_recommendations[:LLM_EXPLANATION_LIMIT]:
        assert recommendation.explanation.startswith("LLM explanation for")
    for recommendation in updated_state.final_recommendations[LLM_EXPLANATION_LIMIT:]:
        assert not recommendation.explanation.startswith("LLM explanation for")


def test_chef_explanation_node_skips_llm_entirely_when_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    recommendations = [_recommendation(str(index)) for index in range(LLM_EXPLANATION_LIMIT - 1)]
    state = MacroChefState(final_recommendations=recommendations)

    call_count = 0

    def _fake_explain_recommendation(recipe, score, allergy_safe=True):
        nonlocal call_count
        call_count += 1
        return f"LLM explanation for {recipe.recipe_id}"

    monkeypatch.setattr(nodes_module, "explain_recommendation", _fake_explain_recommendation)

    result = chef_explanation_node(state)
    updated_state = MacroChefState.model_validate(result)

    assert call_count == LLM_EXPLANATION_LIMIT - 1
    for recommendation in updated_state.final_recommendations:
        assert recommendation.explanation
