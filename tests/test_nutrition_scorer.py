from app.schemas.inventory import ConfirmedIngredient
from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.nutrition_scorer import macro_fit_score, pantry_match_score, score_recipe


def _grounded(**per_serving) -> RecipeNutrition:
    macros = FoodMacros(**per_serving)
    return RecipeNutrition(
        status=GroundingStatus.GROUNDED,
        servings=1,
        total=macros,
        per_serving=macros,
        coverage=1.0,
    )


def _recipe(**kwargs) -> Recipe:
    defaults = {
        "recipe_id": "r",
        "title": "Macro Recipe",
        "ingredients": ["chicken breast", "rice", "spinach", "bell pepper"],
        "instructions": ["Cook."],
        "allergens": [],
        "diet_tags": [],
        "cook_time_min": 20,
        # Self-reported tag macros -- realistic filler only. The scorer must
        # never read these (see test_macro_fit_ignores_tag_macros_*): the
        # perfect/poor-match tests below rely solely on `nutrition`.
        "calories": 500,
        "protein_g": 40,
        "carbs_g": 50,
        "fat_g": 15,
        "fiber_g": 8,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


def test_scores_perfect_macro_match_high() -> None:
    recipe = _recipe(nutrition=_grounded(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8))
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) == 1.0


def test_scores_poor_macro_match_lower() -> None:
    # Tag calories are left at the "perfect" 500/40/50/15/8 filler from
    # _recipe() defaults -- the computed nutrition below is the mismatched
    # one, so this only passes if the scorer reads nutrition, not tags.
    recipe = _recipe(
        nutrition=_grounded(calories=900, protein_g=10, carbs_g=120, fat_g=45, fiber_g=2)
    )
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) < 0.5


def test_macro_fit_neutral_when_ungrounded() -> None:
    # Tag macros are a perfect match for targets, but with no `nutrition` at
    # all the recipe must score neutral, never off the self-reported tag.
    recipe = _recipe(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) == 0.5


def test_macro_fit_neutral_when_partial() -> None:
    partial = RecipeNutrition(
        status=GroundingStatus.PARTIAL,
        servings=1,
        total=FoodMacros(calories=300, protein_g=20, carbs_g=30, fat_g=8, fiber_g=4),
        per_serving=FoodMacros(calories=300, protein_g=20, carbs_g=30, fat_g=8, fiber_g=4),
        ungrounded_ingredients=["mystery sauce"],
        coverage=0.5,
    )
    recipe = _recipe(nutrition=partial)
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    # PARTIAL undercounts (only sums grounded ingredients) -- trusting it here
    # would read as falsely low-calorie, so it must stay neutral like UNGROUNDED.
    assert macro_fit_score(recipe, targets) == 0.5


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
    recipe = _recipe(nutrition=_grounded(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8))
    inventory = [ConfirmedIngredient(name="chicken breast"), ConfirmedIngredient(name="rice")]
    profile = UserProfile(
        user_id="u",
        macro_targets=MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8),
        max_cook_time_min=30,
    )

    score = score_recipe(recipe, inventory, profile)

    assert score.final_score > 0.6
    assert score.macro_fit_score == 1.0
