"""Unit tests for app.services.day_planner (roadmap item B3).

Covers the acceptance criteria from the B3 task spec:
- assemble_plan finds the true optimum on a small hand-constructed
  candidate set with a known-feasible target.
- assemble_plan correctly returns within_tolerance=False + the closest
  plan when nothing fits.
- assemble_plan never includes a PARTIAL/UNGROUNDED/flagged-GROUNDED
  recipe, even when one is a tempting "perfect fit" on paper -- proving
  the trust boundary (app.services.nutrition_view.trusted_per_serving) is
  actually enforced, not just documented.
- assemble_plan respects max_per_recipe.
- assemble_remaining_meal (the K=1 "remaining macros" wrapper) behaves as
  exactly the K=1 case of the general primitive.
- assemble_day_plan sweeps meals_range and returns the globally best
  DayPlan.
"""

from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets
from app.services.day_planner import (
    MacroTolerance,
    assemble_day_plan,
    assemble_plan,
    assemble_remaining_meal,
)


def _nutrition(
    status: GroundingStatus, *, flags: list[str] | None = None, **per_serving
) -> RecipeNutrition:
    macros = FoodMacros(**per_serving)
    return RecipeNutrition(
        status=status,
        servings=1,
        total=macros,
        per_serving=macros,
        coverage=1.0 if status == GroundingStatus.GROUNDED else 0.5,
        flags=flags or [],
    )


def _recipe(recipe_id: str, nutrition: RecipeNutrition | None, **overrides) -> Recipe:
    fields = {
        "recipe_id": recipe_id,
        "title": overrides.pop("title", recipe_id),
        "ingredients": [],
        "instructions": ["Cook."],
        "nutrition": nutrition,
    }
    fields.update(overrides)
    return Recipe(**fields)


def _trusted(recipe_id: str, *, calories: float, protein_g: float, carbs_g=0, fat_g=0, fiber_g=0) -> Recipe:
    return _recipe(
        recipe_id,
        _nutrition(
            GroundingStatus.GROUNDED,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            fiber_g=fiber_g,
        ),
    )


# ---------------------------------------------------------------------------
# True optimum on a known-feasible target.
# ---------------------------------------------------------------------------


def test_finds_true_optimum_on_known_feasible_target() -> None:
    a = _trusted("a", calories=300, protein_g=20)
    b = _trusted("b", calories=500, protein_g=40)
    c = _trusted("c", calories=900, protein_g=10)  # a decoy that could look tempting alone
    target = MacroTargets(calories=800, protein_g=60)  # exactly a + b

    plan = assemble_plan([a, b, c], target, meals=2, max_per_recipe=2)

    assert plan.within_tolerance is True
    assert plan.calories_relative_error == 0.0
    assert plan.protein_relative_error == 0.0
    selected = {item.recipe_id: item.servings for item in plan.items}
    assert selected == {"a": 1, "b": 1}
    assert plan.trusted_pool_size == 3
    assert plan.meals_planned == 2


# ---------------------------------------------------------------------------
# Nothing fits -> within_tolerance False + closest plan, never a silent hit.
# ---------------------------------------------------------------------------


def test_returns_closest_plan_when_nothing_fits() -> None:
    a = _trusted("a", calories=100, protein_g=5)
    b = _trusted("b", calories=150, protein_g=8)
    # Way beyond anything two servings of a/b (capped at 2 each) can reach.
    target = MacroTargets(calories=5000, protein_g=400)

    plan = assemble_plan([a, b], target, meals=2, max_per_recipe=2)

    assert plan.within_tolerance is False
    # Best achievable under meals=2, max_per_recipe=2 is b+b (highest macros).
    selected = {item.recipe_id: item.servings for item in plan.items}
    assert selected == {"b": 2}
    assert plan.total_calories == 300
    assert plan.total_protein_g == 16


# ---------------------------------------------------------------------------
# Trust boundary: PARTIAL/UNGROUNDED/flagged-GROUNDED never selected, even
# when they would be a "perfect" macro match on paper.
# ---------------------------------------------------------------------------


def test_never_selects_untrusted_candidate_even_when_it_is_a_perfect_fit() -> None:
    target = MacroTargets(calories=300, protein_g=20)

    trusted_but_far = _trusted("trusted_far", calories=900, protein_g=90)
    flagged_perfect = _recipe(
        "flagged_perfect",
        _nutrition(
            GroundingStatus.GROUNDED,
            flags=["implausible_kcal_per_serving"],
            calories=300,
            protein_g=20,
            carbs_g=0,
            fat_g=0,
            fiber_g=0,
        ),
    )
    partial_perfect = _recipe(
        "partial_perfect",
        _nutrition(GroundingStatus.PARTIAL, calories=300, protein_g=20, carbs_g=0, fat_g=0, fiber_g=0),
    )
    ungrounded_perfect = _recipe(
        "ungrounded_perfect",
        _nutrition(GroundingStatus.UNGROUNDED, calories=300, protein_g=20, carbs_g=0, fat_g=0, fiber_g=0),
    )
    no_nutrition_at_all = _recipe("no_nutrition", None)

    candidates = [
        trusted_but_far,
        flagged_perfect,
        partial_perfect,
        ungrounded_perfect,
        no_nutrition_at_all,
    ]

    plan = assemble_plan(candidates, target, meals=1, max_per_recipe=2)

    # Only ONE recipe in the candidate list is actually trusted -- the
    # planner must fall back to it (a bad fit) rather than "cheat" via any
    # of the four untrusted-but-perfect-looking recipes.
    assert plan.trusted_pool_size == 1
    selected_ids = {item.recipe_id for item in plan.items}
    assert selected_ids == {"trusted_far"}
    assert "flagged_perfect" not in selected_ids
    assert "partial_perfect" not in selected_ids
    assert "ungrounded_perfect" not in selected_ids
    assert "no_nutrition" not in selected_ids
    # trusted_far is nowhere near the target -- confirms the planner didn't
    # somehow still land on a perfect (0-error) result by cheating.
    assert plan.within_tolerance is False
    assert plan.calories_relative_error > 0.0


# ---------------------------------------------------------------------------
# max_per_recipe is respected, including the combinatorially-infeasible case.
# ---------------------------------------------------------------------------


def test_respects_max_per_recipe_cap() -> None:
    a = _trusted("a", calories=300, protein_g=20)
    target = MacroTargets(calories=600, protein_g=40)  # exactly a * 2

    # cap=2 allows exactly the feasible a+a combo.
    plan_cap2 = assemble_plan([a], target, meals=2, max_per_recipe=2)
    assert plan_cap2.within_tolerance is True
    assert {item.recipe_id: item.servings for item in plan_cap2.items} == {"a": 2}

    # cap=1 makes meals=2 combinatorially infeasible with only one trusted
    # candidate -- must return the explicit "cannot assemble" result, never
    # silently violate the cap to reach the target.
    plan_cap1 = assemble_plan([a], target, meals=2, max_per_recipe=1)
    assert plan_cap1.items == []
    assert plan_cap1.meals_planned == 0
    assert plan_cap1.within_tolerance is False
    assert plan_cap1.total_calories == 0.0


# ---------------------------------------------------------------------------
# assemble_remaining_meal is exactly the K=1 case of assemble_plan.
# ---------------------------------------------------------------------------


def test_remaining_meal_wrapper_matches_k1_general_primitive() -> None:
    a = _trusted("a", calories=300, protein_g=20)
    b = _trusted("b", calories=500, protein_g=40)
    remaining_target = MacroTargets(calories=480, protein_g=38)

    wrapper_plan = assemble_remaining_meal([a, b], remaining_target, max_per_recipe=2)
    direct_plan = assemble_plan([a, b], remaining_target, meals=1, max_per_recipe=2)

    assert wrapper_plan == direct_plan


# ---------------------------------------------------------------------------
# assemble_day_plan sweeps meals_range and returns the globally best result.
# ---------------------------------------------------------------------------


def test_assemble_day_plan_sweeps_and_returns_global_best() -> None:
    a = _trusted("a", calories=300, protein_g=20)
    target = MacroTargets(calories=900, protein_g=60)  # exact fit only at K=3

    plan = assemble_day_plan([a], target, meals_range=(2, 3, 4), max_per_recipe=3)

    assert plan.within_tolerance is True
    assert plan.meals_planned == 3
    assert {item.recipe_id: item.servings for item in plan.items} == {"a": 3}


# ---------------------------------------------------------------------------
# Guardrails: target must specify calories and protein_g.
# ---------------------------------------------------------------------------


def test_raises_without_calories_or_protein_target() -> None:
    a = _trusted("a", calories=300, protein_g=20)
    try:
        assemble_plan([a], MacroTargets(calories=300), meals=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a target missing protein_g")

    try:
        assemble_plan([a], MacroTargets(protein_g=20), meals=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a target missing calories")


def test_default_tolerance_matches_pre_registered_values() -> None:
    assert MacroTolerance().kcal_pct == 0.10
    assert MacroTolerance().protein_pct == 0.15


def test_empty_trusted_pool_returns_explicit_cannot_assemble_result() -> None:
    untrusted = _recipe(
        "untrusted", _nutrition(GroundingStatus.PARTIAL, calories=400, protein_g=30, carbs_g=0, fat_g=0, fiber_g=0)
    )
    target = MacroTargets(calories=400, protein_g=30)

    plan = assemble_plan([untrusted], target, meals=1, max_per_recipe=2)

    assert plan.trusted_pool_size == 0
    assert plan.items == []
    assert plan.within_tolerance is False
