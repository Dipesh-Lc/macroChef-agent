from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.nutrition_scorer import macro_fit_score, pantry_match_score, score_recipe


def _recipe(**kwargs) -> Recipe:
    defaults = {
        "recipe_id": "r",
        "title": "Macro Recipe",
        "ingredients": ["chicken breast", "rice", "spinach", "bell pepper"],
        "instructions": ["Cook."],
        "allergens": [],
        "diet_tags": [],
        "cook_time_min": 20,
        "calories": 500,
        "protein_g": 40,
        "carbs_g": 50,
        "fat_g": 15,
        "fiber_g": 8,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


def test_scores_perfect_macro_match_high() -> None:
    recipe = _recipe()
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) == 1.0


def test_scores_poor_macro_match_lower() -> None:
    recipe = _recipe(calories=900, protein_g=10, carbs_g=120, fat_g=45, fiber_g=2)
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) < 0.5


def test_calculates_pantry_match_correctly() -> None:
    recipe = _recipe()
    inventory = [
        ConfirmedIngredient(name="chicken breast"),
        ConfirmedIngredient(name="rice"),
    ]

    score, used, missing = pantry_match_score(recipe, inventory)

    assert score == 0.5
    assert used == ["chicken breast", "rice"]
    assert missing == ["spinach", "bell pepper"]


def test_pantry_used_missing_amount_aware() -> None:
    # Enough chicken, but short on rice -> rice counts as missing despite being present.
    recipe = _recipe(ingredients=["500 g chicken breast", "300 g rice"])
    inventory = [
        ConfirmedIngredient(name="chicken breast", amount=600, unit="g"),
        ConfirmedIngredient(name="rice", amount=100, unit="g"),
    ]

    score, used, missing = pantry_match_score(recipe, inventory)

    assert used == ["chicken breast"]
    assert missing == ["rice"]
    assert score == 0.5


def test_score_recipe_returns_breakdown() -> None:
    recipe = _recipe()
    inventory = [ConfirmedIngredient(name="chicken breast"), ConfirmedIngredient(name="rice")]
    profile = UserProfile(
        user_id="u",
        macro_targets=MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8),
        max_cook_time_min=30,
    )

    score = score_recipe(recipe, inventory, profile)

    assert score.final_score > 0.6
    assert score.macro_fit_score == 1.0
