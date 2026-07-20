"""Deterministic macro-targeted day-plan assembly (roadmap item B3).

THE HARD SAFETY INVARIANT (do not weaken): this module operates strictly
downstream of app.services.constraint_engine.validate_recipe. It never
calls, reimplements, inspects allergen fields for, second-guesses, or
bypasses that decision -- callers (see app.api.routes_day_planner) MUST
pass only already-safety-cleared recipes into `assemble_plan` /
`assemble_day_plan` / `assemble_remaining_meal`. This module has no
knowledge of allergies, diet type, or any other safety-relevant field; it
only reads macros, and only through
`app.services.nutrition_view.trusted_per_serving`, which is this module's
SOLE trust chokepoint -- PARTIAL, UNGROUNDED, and flagged-GROUNDED recipes
are silently dropped from the candidate pool rather than trusted (see
nutrition_view's own docstring for why). Never read
`recipe.nutrition.per_serving` directly and never fall back to the
self-reported tag macros (`recipe.calories` etc).

No LLM call anywhere in this file, and none should ever be added here -- an
LLM may at most phrase an ALREADY-assembled DayPlan afterward; it may never
choose, rank, or filter the plan's contents (CLAUDE.md's core invariant).

ALGORITHM (design consult, decided -- do not swap without a fresh consult):
exhaustive enumeration over combinations-with-replacement of the trusted
candidate pool, capped at `max_per_recipe` uses of any one recipe. With
today's trusted pool at ~15 recipes (see the crux finding below) and K in
[1, 4], the full solution space is at most C(pool + K - 1, K) combinations
-- a few thousand at the current pool size -- so brute force is provably
optimal, fully deterministic, and fast enough that no optimization library
(pulp/ortools/cvxpy) is justified; this repo's only numerical deps stay
numpy/pandas. Structured as enumerate-then-score so a future swap to a
smarter search (branch-and-bound / DP) only has to replace
`_enumerate_multisets`. See docs/BACKLOG.md for the pre-registered trigger
(~200 trusted recipes) to actually do that swap.

THE CRUX FINDING this module was designed around: as of the A3 corpus
(3,878 recipes), `app.services.nutrition_view.trusted_per_serving` returns
a real number for exactly ~15 recipes -- everything else is PARTIAL
(undercounts) or UNGROUNDED. The solver's real-world candidate universe is
therefore small; see scripts/evaluate_day_planner.py and docs/BACKLOG.md
for the honest consequence (the realistic-round eval bucket may
legitimately report low feasibility until grounding coverage improves --
that is not a bug in this module).

WHOLE-SERVINGS ONLY (v1): selection is by whole recipe servings, never a
fractional/continuous scale factor. Continuous scaling (which could reuse
B2's app.schemas.ingredient.scale_ingredients) would make the +/-10%/
+/-15% tolerance trivially satisfiable for almost any target and gut the
eval's meaning -- see docs/BACKLOG.md for that as an explicit,
deliberately-deferred follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations_with_replacement

from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.nutrition import FoodMacros
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets
from app.services.nutrition_view import trusted_per_serving


@dataclass(frozen=True)
class MacroTolerance:
    """Pre-registered tolerance (B3 design consult, fixed -- do not tune
    after seeing eval results). A plan "fits" iff summed kcal is within
    `kcal_pct` of target calories AND summed protein is within
    `protein_pct` of target protein_g. Secondary macros never gate."""

    kcal_pct: float = 0.10
    protein_pct: float = 0.15


DEFAULT_TOLERANCE = MacroTolerance()

# "day plan" mode sweeps this range of meal counts (recipe-servings) and
# returns the single globally best DayPlan across all of them -- see
# assemble_day_plan.
DEFAULT_MEALS_RANGE: tuple[int, ...] = (2, 3, 4)


def _dedupe_trusted(candidates: list[Recipe]) -> list[tuple[Recipe, FoodMacros]]:
    """The one place `assemble_plan` reads macros: only recipes
    `trusted_per_serving` returns a real value for ever enter the pool.
    PARTIAL/UNGROUNDED/flagged-GROUNDED candidates are silently dropped,
    never padded in. De-duplicates by `recipe_id` (first occurrence wins)
    so a caller accidentally passing the same recipe twice can't inflate
    its effective multiplicity beyond `max_per_recipe`."""
    seen: set[str] = set()
    pool: list[tuple[Recipe, FoodMacros]] = []
    for recipe in candidates:
        if recipe.recipe_id in seen:
            continue
        macros = trusted_per_serving(recipe)
        if macros is None:
            continue
        seen.add(recipe.recipe_id)
        pool.append((recipe, macros))
    return pool


def _enumerate_multisets(pool_size: int, k: int, max_per_recipe: int) -> list[dict[int, int]]:
    """Every multiset of size `k` drawn from `pool_size` distinct recipe
    slots (indices), with any one index appearing at most `max_per_recipe`
    times. `combinations_with_replacement` already yields each multiset
    exactly once (non-decreasing index tuples) -- the cap is applied as a
    post-filter. Empty list means the request is combinatorially infeasible
    (e.g. k > max_per_recipe * pool_size); the caller treats that the same
    as an empty trusted pool -- an explicit "cannot assemble" result, never
    a padded guess."""
    if k <= 0 or pool_size <= 0:
        return []
    combos: list[dict[int, int]] = []
    for combo in combinations_with_replacement(range(pool_size), k):
        counts: dict[int, int] = {}
        for idx in combo:
            counts[idx] = counts.get(idx, 0) + 1
        if all(count <= max_per_recipe for count in counts.values()):
            combos.append(counts)
    return combos


def _relative_error(total: float, target_value: float) -> float:
    """abs(total - target) / target, except at target == 0 where a ratio is
    undefined: 0.0 error if the total is also exactly 0 (a perfect, if
    degenerate, match), else +inf (any nonzero total misses a zero target by
    an unbounded relative amount)."""
    if target_value == 0:
        return 0.0 if total == 0 else float("inf")
    return abs(total - target_value) / target_value


def _optional_relative_error(total: float, target_value: float | None) -> float | None:
    if target_value is None:
        return None
    return _relative_error(total, target_value)


def _build_day_plan(
    pool: list[tuple[Recipe, FoodMacros]],
    combo_counts: dict[int, int],
    target: MacroTargets,
    trusted_pool_size: int,
    tolerance: MacroTolerance,
) -> DayPlan:
    items: list[PlanItem] = []
    total_calories = total_protein_g = total_carbs_g = total_fat_g = total_fiber_g = 0.0
    meals_planned = 0
    for idx in sorted(combo_counts):
        recipe, macros = pool[idx]
        count = combo_counts[idx]
        items.append(PlanItem(recipe_id=recipe.recipe_id, title=recipe.title, servings=count))
        total_calories += macros.calories * count
        total_protein_g += macros.protein_g * count
        total_carbs_g += macros.carbs_g * count
        total_fat_g += macros.fat_g * count
        total_fiber_g += macros.fiber_g * count
        meals_planned += count

    # target.calories/protein_g are guaranteed non-None here -- assemble_plan
    # raises ValueError up front otherwise (the tolerance gate is undefined
    # without both).
    calories_relative_error = _relative_error(total_calories, float(target.calories))
    protein_relative_error = _relative_error(total_protein_g, float(target.protein_g))
    within_tolerance = (
        calories_relative_error <= tolerance.kcal_pct
        and protein_relative_error <= tolerance.protein_pct
    )

    return DayPlan(
        items=items,
        meals_planned=meals_planned,
        trusted_pool_size=trusted_pool_size,
        total_calories=total_calories,
        total_protein_g=total_protein_g,
        total_carbs_g=total_carbs_g,
        total_fat_g=total_fat_g,
        total_fiber_g=total_fiber_g,
        target_calories=float(target.calories),
        target_protein_g=float(target.protein_g),
        calories_relative_error=calories_relative_error,
        protein_relative_error=protein_relative_error,
        carbs_relative_error=_optional_relative_error(total_carbs_g, target.carbs_g),
        fat_relative_error=_optional_relative_error(total_fat_g, target.fat_g),
        fiber_relative_error=_optional_relative_error(total_fiber_g, target.fiber_g),
        within_tolerance=within_tolerance,
    )


def _plan_sort_key(plan: DayPlan) -> tuple[int, float, float]:
    """within_tolerance plans always outrank out-of-tolerance ones; within
    the same tolerance bucket, lower kcal relative error wins first (kcal is
    primary, per the B3 eval design), protein relative error breaks ties."""
    return (0 if plan.within_tolerance else 1, plan.calories_relative_error, plan.protein_relative_error)


def assemble_plan(
    candidates: list[Recipe],
    target: MacroTargets,
    meals: int,
    *,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
) -> DayPlan:
    """The one primitive (B3 design consult). Exhaustively enumerates every
    way to pick `meals` whole recipe-servings from the TRUSTED subset of
    `candidates` (any one recipe used at most `max_per_recipe` times) and
    returns the provably-best DayPlan under `_plan_sort_key` -- an
    in-tolerance plan if one exists, else the closest out-of-tolerance one
    (`within_tolerance=False`, never silently presented as a hit).

    `meals` here means "recipe-servings assembled", not calendar meal slots
    -- "remaining macros" mode is exactly `meals=1` (see
    `assemble_remaining_meal`); "day plan" mode sweeps this over a small
    range (see `assemble_day_plan`).

    Trust boundary: reads macros ONLY via
    `app.services.nutrition_view.trusted_per_serving` -- PARTIAL,
    UNGROUNDED, and flagged-GROUNDED candidates are dropped before any
    combination is built, never selected.

    Safety boundary: `candidates` MUST already be safety-cleared by
    `app.services.constraint_engine.validate_recipe` before calling this --
    this function has no allergy/diet awareness at all and will happily
    select an unsafe recipe if handed one; see
    `app.api.routes_day_planner.plan_day` for the mandatory filtering step.
    """
    if meals < 0:
        raise ValueError("meals must be >= 0")
    if max_per_recipe < 1:
        raise ValueError("max_per_recipe must be >= 1")
    if target.calories is None or target.protein_g is None:
        raise ValueError(
            "assemble_plan requires target.calories and target.protein_g -- "
            "the pre-registered +/-10%/+/-15% tolerance gate (B3 design) is "
            "undefined without both."
        )

    pool = _dedupe_trusted(candidates)
    trusted_pool_size = len(pool)

    if meals == 0:
        combos: list[dict[int, int]] = [{}]
    else:
        combos = _enumerate_multisets(trusted_pool_size, meals, max_per_recipe)
        if not combos:
            # Combinatorially infeasible (empty trusted pool, or meals >
            # max_per_recipe * trusted_pool_size) -- explicit "cannot
            # assemble" result, never a padded guess.
            combos = [{}]

    plans = [_build_day_plan(pool, combo, target, trusted_pool_size, tolerance) for combo in combos]
    return min(plans, key=_plan_sort_key)


def assemble_remaining_meal(
    candidates: list[Recipe],
    remaining_target: MacroTargets,
    *,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
) -> DayPlan:
    """"Remaining macros" mode: the K=1 case of `assemble_plan`, called
    reactively with whatever macros are still needed today (target minus
    what's already been eaten) as `remaining_target`. Thin wrapper only --
    no separate algorithm, per the B3 design consult."""
    return assemble_plan(
        candidates,
        remaining_target,
        meals=1,
        max_per_recipe=max_per_recipe,
        tolerance=tolerance,
    )


def assemble_day_plan(
    candidates: list[Recipe],
    target: MacroTargets,
    *,
    meals_range: tuple[int, ...] = DEFAULT_MEALS_RANGE,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
) -> DayPlan:
    """"Day plan" mode: sweeps `assemble_plan` over `meals_range` (default
    2-4 recipe-servings) and returns the single globally best DayPlan across
    every K tried, per `_plan_sort_key`. Thin wrapper only -- no separate
    algorithm, per the B3 design consult."""
    if not meals_range:
        raise ValueError("meals_range must be non-empty")
    plans = [
        assemble_plan(candidates, target, k, max_per_recipe=max_per_recipe, tolerance=tolerance)
        for k in meals_range
    ]
    return min(plans, key=_plan_sort_key)
