from app.graph.builder import run_recommendation_graph
from app.schemas.recommendation import RecommendationRequest
from app.schemas.user import MacroTargets, UserProfile
from app.services.constraint_engine import validate_recipe


def test_full_graph_with_text_input_produces_safe_recommendations() -> None:
    profile = UserProfile(
        user_id="demo_user",
        allergies=["peanut"],
        disliked_ingredients=[],
        diet_type=None,
        preferred_cuisines=["Thai"],
        macro_targets=MacroTargets(calories=600, protein_g=40, carbs_g=60, fat_g=20, fiber_g=8),
        max_cook_time_min=40,
    )
    request = RecommendationRequest(
        user_id="demo_user",
        input_type="text",
        typed_ingredients="chicken breast, rice, bell pepper, spinach",
        user_profile=profile,
        cuisine_preference="Thai",
        meal_type="dinner",
    )

    response = run_recommendation_graph(request)

    assert response.recommendations
    assert len(response.recommendations) <= 3
    assert response.debug_trace
    assert any("inventory_confirmation_node" in item for item in response.debug_trace)
    assert not response.errors
    for recommendation in response.recommendations:
        assert validate_recipe(recommendation.recipe, profile).is_valid
        assert "peanut" not in [item.lower() for item in recommendation.recipe.allergens]


def test_full_graph_with_mixed_text_and_image_inventory() -> None:
    profile = UserProfile(
        user_id="demo_user",
        allergies=[],
        disliked_ingredients=[],
        diet_type=None,
        preferred_cuisines=[],
        macro_targets=MacroTargets(calories=600, protein_g=35, carbs_g=60, fat_g=20),
        max_cook_time_min=45,
    )
    request = RecommendationRequest(
        user_id="demo_user",
        input_type="mixed",
        typed_ingredients="chicken breast, spinach, rice",
        image_path="vegetarian_pantry_upload.png",
        user_profile=profile,
        meal_type="dinner",
    )

    response = run_recommendation_graph(request)
    inventory_names = {item.normalized_name for item in response.inventory_observations}

    assert response.recommendations
    assert {"chicken breast", "spinach", "rice", "tofu", "broccoli"}.issubset(inventory_names)
    assert response.debug_trace
