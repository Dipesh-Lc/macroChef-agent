"""Unit tests for app.services.weekly_planner (Phase 4 item 2: full weekly
meal-plan solver).

Covers the acceptance criteria from the task spec:
- assemble_week calls app.services.day_planner.assemble_day_plan exactly
  `days` times (spy via monkeypatch).
- With a tiny trusted pool, all `days` DayPlans are structurally identical
  -- the documented, honest "identical days" limitation, not a bug.
- pantry-utilization is computed correctly on a hand-verified synthetic
  case that includes an incomparable (to_grams=None) ingredient, confirming
  it's excluded from both numerator/denominator and counted separately.
- THE RECONCILIATION GATE TEST: two days share a recipe/ingredient, the
  pantry covers ONE day's worth of need but not two -- the actual weekly
  shopping list must match the hand-computed SUM-across-days shortfall
  exactly (the direct test against the B4 double-counting bug class).
"""

import pytest

import app.services.weekly_planner as weekly_planner_module
from app.schemas.day_plan import PlanItem
from app.schemas.ingredient import Ingredient
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets
from app.services.procurement_service import build_shopping_list_for_items
from app.services.weekly_planner import assemble_week, compute_pantry_utilization


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


def _trusted_recipe(
    recipe_id: str,
    *,
    calories: float,
    protein_g: float,
    ingredients: list[Ingredient] | None = None,
    servings: int = 1,
) -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=recipe_id,
        servings=servings,
        ingredients=ingredients or [],
        instructions=["Cook."],
        nutrition=_nutrition(GroundingStatus.GROUNDED, calories=calories, protein_g=protein_g, carbs_g=0, fat_g=0, fiber_g=0),
    )


# ---------------------------------------------------------------------------
# assemble_week calls assemble_day_plan exactly `days` times.
# ---------------------------------------------------------------------------


def test_assemble_week_calls_assemble_day_plan_exactly_days_times(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.schemas.day_plan import DayPlan

    call_count = 0

    def _fake_assemble_day_plan(candidates, target, *, meals_range, max_per_recipe, tolerance):
        nonlocal call_count
        call_count += 1
        return DayPlan(
            items=[],
            meals_planned=0,
            trusted_pool_size=0,
            total_calories=0,
            total_protein_g=0,
            total_carbs_g=0,
            total_fat_g=0,
            total_fiber_g=0,
            target_calories=float(target.calories),
            target_protein_g=float(target.protein_g),
            calories_relative_error=0.0,
            protein_relative_error=0.0,
            within_tolerance=False,
        )

    monkeypatch.setattr(weekly_planner_module, "assemble_day_plan", _fake_assemble_day_plan)

    target = MacroTargets(calories=300, protein_g=20)
    plan = assemble_week([], target, days=5)

    assert call_count == 5
    assert len(plan.days) == 5


# ---------------------------------------------------------------------------
# "Identical days" -- the documented, honest limitation.
# ---------------------------------------------------------------------------


def test_tiny_pool_produces_structurally_identical_days() -> None:
    # Per-serving 150 kcal / 10 g protein -- K=2 (default meals_range sweeps
    # 2/3/4) hits the 300 kcal / 20 g protein target exactly.
    recipe = _trusted_recipe("only", calories=150, protein_g=10)
    target = MacroTargets(calories=300, protein_g=20)

    plan = assemble_week([recipe], target, days=7)

    assert len(plan.days) == 7
    first_items = plan.days[0].items
    assert first_items == [PlanItem(recipe_id="only", title="only", servings=2)]
    for day in plan.days[1:]:
        assert day.items == first_items
        assert day.within_tolerance == plan.days[0].within_tolerance
        assert day.total_calories == plan.days[0].total_calories
        assert day.total_protein_g == plan.days[0].total_protein_g


# ---------------------------------------------------------------------------
# Pantry-utilization: hand-verified, including one incomparable ingredient.
# ---------------------------------------------------------------------------


def test_pantry_utilization_hand_verified_with_incomparable_ingredient() -> None:
    # "rice" -- comparable (mass unit, converts cleanly).
    # "garnish" -- unit "sprig" has no known density/piece-weight -> to_grams
    # returns None -> incomparable, must be excluded from both num/denom and
    # counted separately.
    recipe = Recipe(
        recipe_id="bowl",
        title="Rice Bowl",
        servings=1,
        ingredients=[
            Ingredient(name="rice", amount=200, unit="g"),
            Ingredient(name="garnish", amount=1, unit="sprig"),
        ],
        instructions=["Cook."],
    )
    # 2 PlanItems, each servings=2, factor = 2/1 = 2 -> 400 g rice needed per
    # PlanItem -> 800 g total rice need across both.
    plan_items = [
        PlanItem(recipe_id="bowl", title="Rice Bowl", servings=2),
        PlanItem(recipe_id="bowl", title="Rice Bowl", servings=2),
    ]
    recipe_lookup = {"bowl": recipe}
    inventory = [ConfirmedIngredient(name="rice", amount=300, unit="g")]

    utilization, uncompared = compute_pantry_utilization(plan_items, recipe_lookup, inventory)

    # Hand computation: need = 800 g rice, pantry has 300 g -> covered =
    # min(800, 300) = 300 -> utilization = 300/800 = 0.375. "garnish" is the
    # one incomparable ingredient -- excluded from num/denom, counted once
    # (it aggregates to ONE combined entry across both PlanItems, not two).
    assert utilization == pytest.approx(0.375)
    assert uncompared == 1


def test_pantry_utilization_no_inventory_is_zero_not_fabricated() -> None:
    recipe = Recipe(
        recipe_id="bowl",
        title="Rice Bowl",
        servings=1,
        ingredients=[Ingredient(name="rice", amount=200, unit="g")],
        instructions=["Cook."],
    )
    plan_items = [PlanItem(recipe_id="bowl", title="Rice Bowl", servings=2)]
    utilization, uncompared = compute_pantry_utilization(plan_items, {"bowl": recipe}, [])
    assert utilization == 0.0
    assert uncompared == 0


def test_assemble_week_reports_pantry_utilization_end_to_end() -> None:
    recipe = _trusted_recipe(
        "bowl",
        calories=150,
        protein_g=10,
        ingredients=[Ingredient(name="rice", amount=200, unit="g")],
    )
    target = MacroTargets(calories=300, protein_g=20)
    inventory = [ConfirmedIngredient(name="rice", amount=300, unit="g")]

    plan = assemble_week([recipe], target, days=2, inventory=inventory)

    # Each day selects 2 servings of "bowl" (K=2 exact match) -> per-day
    # need = 200 * (2/1) = 400 g rice; 2 days -> 800 g total need; pantry
    # has 300 g -> utilization = 300/800 = 0.375, matching the unit-level
    # computation above.
    assert plan.pantry_utilization == pytest.approx(0.375)
    assert plan.uncompared_ingredient_count == 0
    assert plan.trusted_pool_size == 1


# ---------------------------------------------------------------------------
# THE RECONCILIATION GATE TEST -- direct test against the B4 double-counting
# bug class, replayed at the week level (pooled PlanItems across 2+ days).
# ---------------------------------------------------------------------------


def test_weekly_shopping_list_sums_shortfall_across_days_not_per_day() -> None:
    # Per-serving 150 kcal / 10 g protein -- K=2 hits 300/20 exactly.
    recipe = _trusted_recipe(
        "tofu_bowl",
        calories=150,
        protein_g=10,
        ingredients=[Ingredient(name="tofu", amount=200, unit="g")],
    )
    target = MacroTargets(calories=300, protein_g=20)
    # Pantry covers exactly ONE day's worth (400 g) but not two.
    inventory = [ConfirmedIngredient(name="tofu", amount=400, unit="g")]

    plan = assemble_week([recipe], target, days=2, inventory=inventory)

    # Sanity: both days identical, each selects 2 servings of tofu_bowl.
    assert plan.days[0].items == [PlanItem(recipe_id="tofu_bowl", title="tofu_bowl", servings=2)]
    assert plan.days[1].items == plan.days[0].items

    # Hand computation: each day needs 200 g * (2 servings / 1 recipe.servings)
    # = 400 g tofu. TWO days -> 800 g total need. Pantry has 400 g -> the
    # TRUE combined shortfall is 800 - 400 = 400 g, in ONE merged line.
    # A naive per-day-then-merge composition would instead see each day's
    # 400 g need independently satisfied by the same undepleted 400 g
    # pantry (400 >= 400, checked separately per day) and wrongly report 0 g
    # shortfall for both days -- exactly the bug class this test catches.
    expected_shortfall = 800.0 - 400.0
    assert expected_shortfall == pytest.approx(400.0)

    pooled_items = [item for day in plan.days for item in day.items]
    recipe_lookup = {"tofu_bowl": recipe}
    shopping_list = build_shopping_list_for_items(pooled_items, recipe_lookup, inventory)

    assert len(shopping_list) == 1
    assert shopping_list[0].name == "tofu"
    assert shopping_list[0].amount == pytest.approx(400.0)
    assert shopping_list[0].unit == "g"

    # Cross-check: assemble_week's own reported pantry_utilization on the
    # SAME scenario must agree (covered = min(800, 400) = 400 -> 400/800 =
    # 0.5), never silently double-counting the same 400 g pantry as
    # covering both days independently.
    assert plan.pantry_utilization == pytest.approx(0.5)
    assert plan.uncompared_ingredient_count == 0


# ---------------------------------------------------------------------------
# Input validation.
# ---------------------------------------------------------------------------


def test_assemble_week_rejects_zero_or_negative_days() -> None:
    target = MacroTargets(calories=300, protein_g=20)
    with pytest.raises(ValueError):
        assemble_week([], target, days=0)
