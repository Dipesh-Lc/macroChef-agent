import pytest

from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.ingredient import Ingredient
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.shopping import ShoppingItem
from app.services.procurement_service import (
    _analyze,
    build_shopping_list_for_plan,
    build_shopping_list_for_recipe,
    merge_shopping_lists,
    split_used_and_missing,
)
from app.utils.unit_converter import to_grams


def _recipe(ingredients: list[str]) -> Recipe:
    return Recipe(recipe_id="r", title="Bowl", ingredients=ingredients)


def test_present_and_sufficient_quantity_is_used() -> None:
    recipe = _recipe(["500 g chicken breast"])
    inventory = [ConfirmedIngredient(name="chicken breast", amount=600, unit="g")]

    used, missing = split_used_and_missing(recipe, inventory)

    assert used == ["chicken breast"]
    assert missing == []
    assert build_shopping_list_for_recipe(recipe, inventory) == []


def test_present_but_short_quantity_is_missing_with_shortfall() -> None:
    recipe = _recipe(["500 g chicken breast"])
    inventory = [ConfirmedIngredient(name="chicken breast", amount=200, unit="g")]

    used, missing = split_used_and_missing(recipe, inventory)
    assert used == []
    assert missing == ["chicken breast"]

    (item,) = build_shopping_list_for_recipe(recipe, inventory)
    assert item.amount == pytest.approx(300)
    assert item.unit == "g"


def test_incomparable_quantity_is_present_uncompared_and_flagged() -> None:
    # Unknown density -> the need can't be converted, so we can't verify the amount.
    recipe = _recipe(["1 cup dragonfruit"])
    inventory = [ConfirmedIngredient(name="dragonfruit", amount=1, unit="cup")]

    (result,) = _analyze(recipe, inventory)
    assert result.status == "present_uncompared"  # flagged, not a silent "satisfied"

    used, missing = split_used_and_missing(recipe, inventory)
    assert used == ["dragonfruit"]
    assert missing == []


def test_name_only_inventory_still_matches() -> None:
    # Pantry item with no amount (legacy) -> present but uncompared, not dropped.
    recipe = _recipe(["500 g chicken breast"])
    inventory = [ConfirmedIngredient(name="chicken breast")]

    (result,) = _analyze(recipe, inventory)
    assert result.status == "present_uncompared"
    assert split_used_and_missing(recipe, inventory) == (["chicken breast"], [])


def test_shopping_list_carries_structured_shortfall() -> None:
    recipe = _recipe(["2 cups rice", "300 g tofu"])
    inventory = [ConfirmedIngredient(name="rice", amount=1, unit="cup")]

    items = {item.name: item for item in build_shopping_list_for_recipe(recipe, inventory)}

    assert items["rice"].amount == pytest.approx(1.0)  # short by one cup
    assert items["rice"].unit == "cup"
    assert "short" in items["rice"].quantity
    # tofu is entirely absent -> full requested amount.
    assert items["tofu"].amount == pytest.approx(300)
    assert items["tofu"].unit == "g"


def test_merge_sums_comparable_shortfalls() -> None:
    items = [
        ShoppingItem(name="rice", amount=200, unit="g", reason="Needed for A"),
        ShoppingItem(name="rice", amount=300, unit="g", reason="Needed for B"),
    ]

    (merged,) = merge_shopping_lists(items)

    assert merged.name == "rice"
    assert merged.amount == pytest.approx(500)
    assert merged.unit == "g"
    assert merged.reason == "Needed for A; Needed for B"


def test_merge_falls_back_when_incomparable() -> None:
    items = [
        ShoppingItem(name="rice", amount=200, unit="g", quantity="short 200 g"),
        ShoppingItem(name="rice", amount=None, unit=None, quantity=None),
    ]

    (merged,) = merge_shopping_lists(items)

    assert merged.amount is None
    assert merged.unit is None


# --- B4: build_shopping_list_for_plan (per-plan aggregation) -----------------


def _day_plan(items: list[PlanItem]) -> DayPlan:
    """Minimal-but-valid DayPlan for shopping-list tests -- the macro totals
    below are irrelevant to procurement_service (which never reads them),
    so they're filled with harmless placeholder values."""
    return DayPlan(
        items=items,
        meals_planned=sum(item.servings for item in items),
        trusted_pool_size=len(items),
        total_calories=0,
        total_protein_g=0,
        total_carbs_g=0,
        total_fat_g=0,
        total_fiber_g=0,
        target_calories=0,
        target_protein_g=0,
        calories_relative_error=0,
        protein_relative_error=0,
        within_tolerance=True,
    )


def test_plan_shopping_list_reconciles_exactly_against_hand_computed_grams() -> None:
    """Reconciliation test (B4 acceptance gate): the merged shopping list's
    quantities equal (plan's total scaled ingredient requirements) minus
    (pantry holdings), computed independently here via the same to_grams
    arithmetic the production code uses."""
    r1 = Recipe(
        recipe_id="r1",
        title="Chicken Rice Bowl",
        servings=1,
        ingredients=[
            Ingredient(name="chicken breast", amount=200, unit="g"),
            Ingredient(name="rice", amount=100, unit="g"),
        ],
    )
    r2 = Recipe(
        recipe_id="r2",
        title="Rice Broccoli Side",
        servings=1,
        ingredients=[
            Ingredient(name="rice", amount=150, unit="g"),
            Ingredient(name="broccoli", amount=80, unit="g"),
        ],
    )
    plan = _day_plan(
        [
            PlanItem(recipe_id="r1", title=r1.title, servings=1),
            PlanItem(recipe_id="r2", title=r2.title, servings=2),  # multiplicity > 1
        ]
    )
    inventory = [
        ConfirmedIngredient(name="chicken breast", amount=50, unit="g"),
        ConfirmedIngredient(name="rice", amount=120, unit="g"),
        # no broccoli on hand at all
    ]
    recipe_lookup = {"r1": r1, "r2": r2}

    # Independently hand-computed (grams), mirroring the production math:
    # r1 contributes 1x its as-written ingredients (servings=1, recipe.servings=1).
    # r2 contributes 2x its as-written ingredients (servings=2, recipe.servings=1).
    need_chicken = 200 * 1
    need_rice = 100 * 1 + 150 * 2
    need_broccoli = 80 * 2

    have_chicken = to_grams(50, "g", name="chicken breast")
    have_rice = to_grams(120, "g", name="rice")
    have_broccoli = 0.0

    expected_short_chicken = need_chicken - have_chicken
    expected_short_rice = need_rice - have_rice
    expected_short_broccoli = need_broccoli - have_broccoli

    assert expected_short_chicken == pytest.approx(150.0)
    assert expected_short_rice == pytest.approx(280.0)
    assert expected_short_broccoli == pytest.approx(160.0)

    shopping_list = build_shopping_list_for_plan(plan, recipe_lookup, inventory)
    by_name = {item.name: item for item in shopping_list}

    assert by_name["chicken breast"].amount == pytest.approx(expected_short_chicken)
    assert by_name["chicken breast"].unit == "g"
    assert by_name["rice"].amount == pytest.approx(expected_short_rice)
    assert by_name["rice"].unit == "g"
    assert by_name["broccoli"].amount == pytest.approx(expected_short_broccoli)
    assert by_name["broccoli"].unit == "g"
    assert len(shopping_list) == 3  # one merged line per ingredient, not per recipe


def test_plan_shopping_list_sums_same_ingredient_across_two_recipes() -> None:
    """The actual point of B4: an ingredient needed by two different plan
    items gets its shortfall SUMMED into one merged line, not left as two
    separate per-recipe lines. Recipe A needs 200 g; recipe B (servings=2,
    150 g as-written) needs 2x150=300 g; pantry has 100 g -> merged shortfall
    is (200 + 300) - 100 = 400 g in a single ShoppingItem."""
    recipe_a = Recipe(
        recipe_id="a",
        title="Tofu Stir Fry",
        servings=1,
        ingredients=[Ingredient(name="tofu", amount=200, unit="g")],
    )
    recipe_b = Recipe(
        recipe_id="b",
        title="Tofu Soup",
        servings=1,
        ingredients=[Ingredient(name="tofu", amount=150, unit="g")],
    )
    plan = _day_plan(
        [
            PlanItem(recipe_id="a", title=recipe_a.title, servings=1),
            PlanItem(recipe_id="b", title=recipe_b.title, servings=2),
        ]
    )
    inventory = [ConfirmedIngredient(name="tofu", amount=100, unit="g")]
    recipe_lookup = {"a": recipe_a, "b": recipe_b}

    shopping_list = build_shopping_list_for_plan(plan, recipe_lookup, inventory)

    assert len(shopping_list) == 1  # merged into a single line, not two
    (item,) = shopping_list
    assert item.name == "tofu"
    assert item.amount == pytest.approx(400.0)
    assert item.unit == "g"
    assert item.reason is not None and "Tofu Stir Fry" in item.reason and "Tofu Soup" in item.reason


def test_plan_shopping_list_scales_by_servings_over_recipe_servings() -> None:
    """PlanItem.servings is a COUNT OF SERVINGS, while Recipe.ingredients is
    written for the whole recipe (yielding recipe.servings servings) -- the
    correct scale factor is item.servings / recipe.servings, not
    item.servings alone. A recipe that yields 4 servings from 400 g flour,
    selected for 2 plan-servings, needs 400 * (2/4) = 200 g flour. An
    ingredient with no declared amount stays unscaled/None -- never
    fabricated (reuses scale_ingredients's existing guarantee)."""
    recipe = Recipe(
        recipe_id="batch",
        title="Big Batch Pancakes",
        servings=4,
        ingredients=[
            Ingredient(name="flour", amount=400, unit="g"),
            Ingredient(name="salt"),  # no amount ("to taste") -- must stay None
        ],
    )
    plan = _day_plan([PlanItem(recipe_id="batch", title=recipe.title, servings=2)])
    inventory: list[ConfirmedIngredient] = []
    recipe_lookup = {"batch": recipe}

    shopping_list = build_shopping_list_for_plan(plan, recipe_lookup, inventory)
    by_name = {item.name: item for item in shopping_list}

    assert by_name["flour"].amount == pytest.approx(200.0)
    assert by_name["flour"].unit == "g"
    # salt has no amount -> missing-with-no-fabricated-quantity, not dropped
    assert by_name["salt"].amount is None
    assert by_name["salt"].quantity is None


def test_plan_shopping_list_skips_plan_item_missing_from_recipe_lookup() -> None:
    """A PlanItem whose recipe_id isn't in recipe_lookup is skipped, never
    fabricated -- it simply contributes nothing to the shopping list."""
    known = Recipe(
        recipe_id="known",
        title="Known Recipe",
        servings=1,
        ingredients=[Ingredient(name="egg", amount=100, unit="g")],
    )
    plan = _day_plan(
        [
            PlanItem(recipe_id="known", title=known.title, servings=1),
            PlanItem(recipe_id="ghost", title="Ghost Recipe", servings=1),
        ]
    )
    shopping_list = build_shopping_list_for_plan(plan, {"known": known}, [])

    assert len(shopping_list) == 1
    assert shopping_list[0].name == "egg"
