"""Unit tests for app.services.batch_planner (Phase 4 item 1: meal-prep
batch solver).

Covers the acceptance criteria from the task spec:
- `_container_eligible` correctly classifies a recipe as eligible/
  ineligible against a known target, and drops (returns None) any recipe
  `trusted_per_serving` can't trust.
- The sort/take-top selection picks the best-fitting recipes.
- `_distribute_containers` verifies the whole-container distribution rule
  (10 / 3 -> 4/3/3, remainder to lowest-error recipes) exactly.
- All three degenerate cases (>= min_recipes eligible, exactly 1 eligible,
  zero eligible) produce the exact documented behavior, plus the
  empty-trusted-pool case.
- Container counts always sum to exactly `containers`.
"""

from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.services.batch_planner import (
    DEFAULT_TOLERANCE,
    _container_eligible,
    _distribute_containers,
    assemble_batch_plan,
)


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
        _nutrition(GroundingStatus.GROUNDED, calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, fiber_g=fiber_g),
    )


# ---------------------------------------------------------------------------
# _container_eligible
# ---------------------------------------------------------------------------


def test_container_eligible_classifies_within_band_recipe_as_eligible() -> None:
    recipe = _trusted("a", calories=500, protein_g=40)
    result = _container_eligible(recipe, target_kcal=500, target_protein=40, tolerance=DEFAULT_TOLERANCE)
    assert result is not None
    is_eligible, kcal_error, protein_error = result
    assert is_eligible is True
    assert kcal_error == 0.0
    assert protein_error == 0.0


def test_container_eligible_classifies_out_of_band_recipe_as_ineligible() -> None:
    # 3x target calories -- way outside the +/-10% band, even though a
    # single macro alone (protein) matches exactly. A floor on one macro
    # must never be enough on its own.
    recipe = _trusted("b", calories=1500, protein_g=40)
    result = _container_eligible(recipe, target_kcal=500, target_protein=40)
    assert result is not None
    is_eligible, kcal_error, protein_error = result
    assert is_eligible is False
    assert kcal_error > DEFAULT_TOLERANCE.kcal_pct
    assert protein_error == 0.0


def test_container_eligible_drops_untrusted_recipe() -> None:
    # PARTIAL nutrition -- trusted_per_serving returns None -- must be
    # dropped (None), never fabricated into a fake eligibility.
    partial = _recipe(
        "c",
        _nutrition(GroundingStatus.PARTIAL, calories=500, protein_g=40, carbs_g=10, fat_g=8, fiber_g=2),
    )
    assert _container_eligible(partial, target_kcal=500, target_protein=40) is None

    ungrounded = _recipe("d", None)
    assert _container_eligible(ungrounded, target_kcal=500, target_protein=40) is None

    flagged = _recipe(
        "e",
        _nutrition(
            GroundingStatus.GROUNDED,
            flags=["implausible_kcal"],
            calories=500,
            protein_g=40,
            carbs_g=10,
            fat_g=8,
            fiber_g=2,
        ),
    )
    assert _container_eligible(flagged, target_kcal=500, target_protein=40) is None


# ---------------------------------------------------------------------------
# _distribute_containers
# ---------------------------------------------------------------------------


def test_distribute_containers_10_over_3_is_4_3_3() -> None:
    assert _distribute_containers(10, 3) == [4, 3, 3]


def test_distribute_containers_even_split() -> None:
    assert _distribute_containers(9, 3) == [3, 3, 3]


def test_distribute_containers_single_recipe_gets_all() -> None:
    assert _distribute_containers(10, 1) == [10]


def test_distribute_containers_always_sums_to_containers() -> None:
    for containers in range(1, 31):
        for count in range(1, 6):
            counts = _distribute_containers(containers, count)
            assert sum(counts) == containers
            assert len(counts) == count
            assert all(c >= 0 for c in counts)
            # never more than a 1-container spread between the largest and
            # smallest share
            assert max(counts) - min(counts) <= 1


# ---------------------------------------------------------------------------
# assemble_batch_plan: sort/take-top selection
# ---------------------------------------------------------------------------


def test_selects_best_fitting_recipes_by_relative_error() -> None:
    perfect = _trusted("perfect", calories=500, protein_g=40)
    close = _trusted("close", calories=520, protein_g=42)  # small error, still eligible
    far_but_eligible = _trusted("far", calories=540, protein_g=44)  # larger error, still eligible
    ineligible = _trusted("bad", calories=2000, protein_g=40)  # way outside band

    plan = assemble_batch_plan(
        [perfect, close, far_but_eligible, ineligible],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=9,
        min_recipes=2,
        max_recipes=3,
    )

    selected_ids = {item.recipe_id for item in plan.items}
    assert selected_ids == {"perfect", "close", "far"}
    assert "bad" not in selected_ids
    assert plan.within_tolerance is True
    assert plan.recipes_selected == 3
    assert plan.trusted_pool_size == 4

    # sorted best-to-worst -> "perfect" (lowest error) must get >= share of
    # any other recipe under the 9/3 == 3/3/3 even split (no remainder here,
    # so this really just proves ordering doesn't get scrambled).
    by_id = {item.recipe_id: item.servings for item in plan.items}
    assert by_id == {"perfect": 3, "close": 3, "far": 3}


def test_max_recipes_caps_selection_to_best_fits() -> None:
    recipes = [
        _trusted("a", calories=500, protein_g=40),  # perfect
        _trusted("b", calories=510, protein_g=41),  # small error
        _trusted("c", calories=530, protein_g=43),  # bigger error, still eligible
        _trusted("d", calories=545, protein_g=44),  # biggest error, still eligible (< 10%/15%)
    ]

    plan = assemble_batch_plan(
        recipes,
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
        min_recipes=2,
        max_recipes=3,
    )

    assert plan.recipes_selected == 3
    selected_ids = {item.recipe_id for item in plan.items}
    # "d" has the worst fit of the four eligible recipes -- must be excluded
    # by the max_recipes=3 cap.
    assert "d" not in selected_ids
    assert selected_ids == {"a", "b", "c"}


def test_container_distribution_gives_extra_to_lowest_error_recipe() -> None:
    best = _trusted("best", calories=500, protein_g=40)  # 0 error
    mid = _trusted("mid", calories=520, protein_g=41)
    worst = _trusted("worst", calories=545, protein_g=44)

    plan = assemble_batch_plan(
        [best, mid, worst],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
        min_recipes=2,
        max_recipes=3,
    )

    by_id = {item.recipe_id: item.servings for item in plan.items}
    assert by_id["best"] == 4  # gets the single remainder container
    assert by_id["mid"] == 3
    assert by_id["worst"] == 3
    assert sum(by_id.values()) == 10


# ---------------------------------------------------------------------------
# Degenerate cases
# ---------------------------------------------------------------------------


def test_at_least_min_recipes_eligible_is_a_normal_within_tolerance_plan() -> None:
    a = _trusted("a", calories=500, protein_g=40)
    b = _trusted("b", calories=505, protein_g=41)
    plan = assemble_batch_plan(
        [a, b],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
        min_recipes=2,
        max_recipes=3,
    )
    assert plan.within_tolerance is True
    assert plan.recipes_selected == 2
    assert sum(item.servings for item in plan.items) == 10


def test_exactly_one_eligible_fills_all_containers_but_flags_below_min_recipes() -> None:
    only_eligible = _trusted("only", calories=500, protein_g=40)
    way_off = _trusted("off", calories=5000, protein_g=400)  # nowhere near tolerance

    plan = assemble_batch_plan(
        [only_eligible, way_off],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
        min_recipes=2,
        max_recipes=3,
    )

    assert plan.within_tolerance is True
    assert plan.recipes_selected == 1  # explicit "variety not achieved" signal
    assert len(plan.items) == 1
    assert plan.items[0].recipe_id == "only"
    assert plan.items[0].servings == 10  # single recipe fills ALL containers


def test_zero_eligible_returns_closest_recipe_out_of_tolerance() -> None:
    closer = _trusted("closer", calories=700, protein_g=40)  # 40% over kcal target
    farther = _trusted("farther", calories=2000, protein_g=40)  # way over

    plan = assemble_batch_plan(
        [closer, farther],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
        min_recipes=2,
        max_recipes=3,
    )

    assert plan.within_tolerance is False
    assert plan.recipes_selected == 1
    assert len(plan.items) == 1
    assert plan.items[0].recipe_id == "closer"  # the CLOSEST, never an empty pad
    assert plan.items[0].servings == 10


def test_empty_trusted_pool_returns_empty_plan_out_of_tolerance() -> None:
    untrusted = _recipe(
        "u", _nutrition(GroundingStatus.PARTIAL, calories=500, protein_g=40, carbs_g=10, fat_g=8, fiber_g=2)
    )

    plan = assemble_batch_plan(
        [untrusted],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
    )

    assert plan.items == []
    assert plan.within_tolerance is False
    assert plan.recipes_selected == 0
    assert plan.trusted_pool_size == 0
    assert plan.recipe_fits == []


def test_no_candidates_at_all_returns_empty_plan() -> None:
    plan = assemble_batch_plan(
        [],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
    )
    assert plan.items == []
    assert plan.within_tolerance is False
    assert plan.trusted_pool_size == 0


# ---------------------------------------------------------------------------
# Container counts always sum to `containers`, across a range of shapes.
# ---------------------------------------------------------------------------


def test_container_counts_always_sum_to_requested_containers() -> None:
    recipes = [
        _trusted("a", calories=500, protein_g=40),
        _trusted("b", calories=505, protein_g=41),
        _trusted("c", calories=510, protein_g=42),
        _trusted("d", calories=515, protein_g=43),
    ]
    for containers in (1, 2, 3, 7, 10, 13, 30):
        plan = assemble_batch_plan(
            recipes,
            per_container_target_calories=500,
            per_container_target_protein_g=40,
            containers=containers,
            min_recipes=2,
            max_recipes=3,
        )
        assert sum(item.servings for item in plan.items) == containers


# ---------------------------------------------------------------------------
# De-duplication (mirrors day_planner's own guarantee).
# ---------------------------------------------------------------------------


def test_duplicate_recipe_ids_are_deduplicated_in_trusted_pool_size() -> None:
    a = _trusted("a", calories=500, protein_g=40)
    a_again = _trusted("a", calories=500, protein_g=40)
    plan = assemble_batch_plan(
        [a, a_again],
        per_container_target_calories=500,
        per_container_target_protein_g=40,
        containers=10,
    )
    assert plan.trusted_pool_size == 1
