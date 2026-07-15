from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.services.nutrition_view import macro_display_state, trusted_per_serving


def _nutrition(status: GroundingStatus, *, flags: list[str] | None = None, **per_serving) -> RecipeNutrition:
    macros = FoodMacros(**per_serving)
    return RecipeNutrition(
        status=status,
        servings=1,
        total=macros,
        per_serving=macros,
        coverage=1.0 if status == GroundingStatus.GROUNDED else 0.5,
        flags=flags or [],
    )


def _recipe(nutrition: RecipeNutrition | None) -> Recipe:
    return Recipe(
        recipe_id="r",
        title="Test Recipe",
        ingredients=[],
        instructions=["Cook."],
        nutrition=nutrition,
    )


def test_no_nutrition_is_unknown() -> None:
    recipe = _recipe(None)
    assert macro_display_state(recipe) == "unknown"
    assert trusted_per_serving(recipe) is None


def test_grounded_with_no_flags_is_trusted() -> None:
    nutrition = _nutrition(GroundingStatus.GROUNDED, calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)
    recipe = _recipe(nutrition)

    assert macro_display_state(recipe) == "grounded"
    assert trusted_per_serving(recipe) == nutrition.per_serving


def test_partial_is_displayed_but_never_trusted_for_scoring() -> None:
    nutrition = _nutrition(GroundingStatus.PARTIAL, calories=300, protein_g=20, carbs_g=30, fat_g=8, fiber_g=4)
    recipe = _recipe(nutrition)

    assert macro_display_state(recipe) == "partial"
    assert trusted_per_serving(recipe) is None


def test_ungrounded_is_unknown() -> None:
    nutrition = _nutrition(GroundingStatus.UNGROUNDED, calories=0, protein_g=0, carbs_g=0, fat_g=0, fiber_g=0)
    recipe = _recipe(nutrition)

    assert macro_display_state(recipe) == "unknown"
    assert trusted_per_serving(recipe) is None


def test_flagged_grounded_recipe_demotes_to_unknown_and_untrusted() -> None:
    # The core phase 1.5/P3 assertion: a demoting flag overrides GROUNDED
    # status for both display and trust, even though every ingredient
    # grounded -- an implausible computed value is not more trustworthy
    # just because coverage is complete.
    nutrition = _nutrition(
        GroundingStatus.GROUNDED,
        flags=["implausible_kcal_per_serving"],
        calories=5000,
        protein_g=40,
        carbs_g=50,
        fat_g=15,
        fiber_g=8,
    )
    recipe = _recipe(nutrition)

    assert macro_display_state(recipe) == "unknown"
    assert trusted_per_serving(recipe) is None


def test_flagged_partial_recipe_stays_unknown_not_partial() -> None:
    # Conservative interpretation of "even at GROUNDED" from the design
    # note: a demoting flag is applied regardless of status, not only when
    # status happens to be GROUNDED -- the safety-first reading is that any
    # flag means "don't trust the display state either."
    nutrition = _nutrition(
        GroundingStatus.PARTIAL,
        flags=["implausible_kcal_per_serving"],
        calories=5000,
        protein_g=40,
        carbs_g=50,
        fat_g=15,
        fiber_g=8,
    )
    recipe = _recipe(nutrition)

    assert macro_display_state(recipe) == "unknown"
    assert trusted_per_serving(recipe) is None
