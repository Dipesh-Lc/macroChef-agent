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

PANTRY-COVERAGE AND DAY-TO-DAY VARIETY TIEBREAKS (2026-07-22 follow-up,
built ahead of the ~200-trusted-recipe revisit trigger docs/BACKLOG.md
pre-registers for this -- see "Day-to-day variety" and "Pantry-utilization
as a scored objective" there -- per the project human's explicit request
on 2026-07-22, who accepted that ties will be rare-to-occasional at
today's pool size). `_plan_sort_key` now has two additional tiers, STRICTLY
BELOW the three pre-existing macro-fit tiers (`within_tolerance`,
`calories_relative_error`, `protein_relative_error`, unchanged, still
first and still primary): a serving-count-weighted count of recipes
already used earlier in the same week (`num_reused_recipes`, ascending --
lower is better), then pantry coverage (`pantry_coverage`, computed by
`app.services.procurement_service.pantry_coverage_fraction`, descending --
higher is better). These are STRICT SUB-MACRO TIEBREAKERS ONLY, never
objectives -- never described as "optimized", "maximized", or "solved"
anywhere (comments, docstrings, API text, UI copy): nothing in this pair
of tiers can ever let a worse-macro-fit plan win over a better one, and
they only ever activate on an EXACT tie (no epsilon/banding of any kind --
banding would silently redefine the already-locked primary tiers, which
stays out of scope). At today's ~15-recipe trusted pool, an exact tie on
both macro-error tiers for these tiebreakers to ever fire on is
rare-to-occasional; in practice they will often change nothing.

Per-endpoint tier visibility: `POST /plan/day` and `POST /plan/remaining-
meal` (via `assemble_plan`/`assemble_day_plan`/`assemble_remaining_meal`
directly) only ever get the pantry tiebreak live -- the variety tier is a
structural no-op there, since `avoid_recipe_ids` is always empty on those
paths (there is no "prior day" concept for a single day-plan/remaining-
meal request). `POST /plan/week` (via `app.services.weekly_planner.
assemble_week`) gets BOTH tiebreaks live: pantry coverage per day, and
variety across the week's days (a cumulative `avoid_recipe_ids` built from
every prior day's selections -- see that module's own docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations_with_replacement

from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.nutrition import FoodMacros
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets
from app.services.nutrition_view import trusted_per_serving
from app.services.procurement_service import pantry_coverage_fraction


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
    inventory: list[ConfirmedIngredient] | None,
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

    # Pantry coverage (REPORTED / TIEBREAK USE ONLY -- see this module's
    # docstring): `None` when no inventory was supplied at all -- honest
    # "nothing to report" rather than a fabricated 0.0 -- vs. a real
    # computed fraction (which can legitimately BE 0.0) once inventory is
    # supplied. `_plan_sort_key` treats a `None` here as a no-op 0.0 in the
    # sort tuple either way (see that function).
    pantry_coverage: float | None = None
    if inventory:
        recipe_counts = [(pool[idx][0], count) for idx, count in combo_counts.items()]
        pantry_coverage, _uncompared = pantry_coverage_fraction(recipe_counts, inventory)

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
        pantry_coverage=pantry_coverage,
    )


def _plan_sort_key(plan: DayPlan, avoid_recipe_ids: frozenset[str]) -> tuple[int, float, float, int, float]:
    """within_tolerance plans always outrank out-of-tolerance ones; within
    the same tolerance bucket, lower kcal relative error wins first (kcal is
    primary, per the B3 eval design), protein relative error breaks ties --
    these first three tiers are UNCHANGED and remain the strict, unweakened
    primary sort (see this module's docstring's pantry/variety-tiebreak
    paragraph for why the two tiers below can never override them).

    Two additional STRICT SUB-MACRO TIEBREAK tiers, only ever consulted on
    an exact tie of the first three (no epsilon/banding):

    - `num_reused_recipes`: serving-count-weighted (NOT a binary "is this
      recipe id present" check) count of servings in `plan.items` whose
      recipe_id is in `avoid_recipe_ids` (recipes already used on an
      earlier day this week -- empty for `/plan/day` and
      `/plan/remaining-meal`, a structural no-op there). Recomputed
      directly from `plan.items` (which already carry `recipe_id` and
      `servings` for the exact combo this plan represents) rather than
      threaded separately, so this stays valid whether `plan` is one
      combo's candidate or an already-chosen best-of-K day plan. Lower is
      better (ascending, same direction as the macro-error terms).
    - `pantry_coverage`: `plan.pantry_coverage` (computed once, in
      `_build_day_plan`, via `app.services.procurement_service.
      pantry_coverage_fraction`), or 0.0 when `None` (no inventory was
      supplied -- a no-op tier that preserves byte-identical ordering to
      before this tiebreak existed). Higher coverage is better, hence the
      negation so ascending sort still works uniformly.
    """
    num_reused_recipes = sum(item.servings for item in plan.items if item.recipe_id in avoid_recipe_ids)
    return (
        0 if plan.within_tolerance else 1,
        plan.calories_relative_error,
        plan.protein_relative_error,
        num_reused_recipes,
        -(plan.pantry_coverage or 0.0),
    )


def assemble_plan(
    candidates: list[Recipe],
    target: MacroTargets,
    meals: int,
    *,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
    avoid_recipe_ids: frozenset[str] = frozenset(),
    inventory: list[ConfirmedIngredient] | None = None,
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

    `avoid_recipe_ids` and `inventory` are both purely additive, DEFAULTED
    keyword-only params (2026-07-22 pantry/variety-tiebreak follow-up, see
    this module's docstring): omitting both is a ZERO-behavior-change
    no-op, byte-identical to this function's pre-existing output --
    `_plan_sort_key`'s two extra tiers only ever activate on an exact tie
    of the unweakened macro-fit tiers, and collapse to a no-op when
    `avoid_recipe_ids` is empty and `inventory` is `None`/empty.
    `avoid_recipe_ids` marks recipes already used on an earlier day this
    week (empty for a single day-plan/remaining-meal call -- see
    `app.services.weekly_planner.assemble_week` for the only caller that
    passes a nonempty set). `inventory` feeds the pantry-coverage tiebreak
    (`app.services.procurement_service.pantry_coverage_fraction`) -- never
    the recipe-selection macro math itself.

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

    plans = [
        _build_day_plan(pool, combo, target, trusted_pool_size, tolerance, inventory) for combo in combos
    ]
    return min(plans, key=lambda plan: _plan_sort_key(plan, avoid_recipe_ids))


def assemble_remaining_meal(
    candidates: list[Recipe],
    remaining_target: MacroTargets,
    *,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
    avoid_recipe_ids: frozenset[str] = frozenset(),
    inventory: list[ConfirmedIngredient] | None = None,
) -> DayPlan:
    """"Remaining macros" mode: the K=1 case of `assemble_plan`, called
    reactively with whatever macros are still needed today (target minus
    what's already been eaten) as `remaining_target`. Thin wrapper only --
    no separate algorithm, per the B3 design consult. `avoid_recipe_ids`/
    `inventory` are pure passthroughs to `assemble_plan` (see its
    docstring) -- both default to a no-op."""
    return assemble_plan(
        candidates,
        remaining_target,
        meals=1,
        max_per_recipe=max_per_recipe,
        tolerance=tolerance,
        avoid_recipe_ids=avoid_recipe_ids,
        inventory=inventory,
    )


def assemble_day_plan(
    candidates: list[Recipe],
    target: MacroTargets,
    *,
    meals_range: tuple[int, ...] = DEFAULT_MEALS_RANGE,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
    avoid_recipe_ids: frozenset[str] = frozenset(),
    inventory: list[ConfirmedIngredient] | None = None,
) -> DayPlan:
    """"Day plan" mode: sweeps `assemble_plan` over `meals_range` (default
    2-4 recipe-servings) and returns the single globally best DayPlan across
    every K tried, per `_plan_sort_key`. Thin wrapper only -- no separate
    algorithm, per the B3 design consult. `avoid_recipe_ids`/`inventory` are
    pure passthroughs to every `assemble_plan` call in the sweep, and also
    used for the final cross-K `_plan_sort_key` comparison (see
    `assemble_plan`'s docstring) -- both default to a no-op."""
    if not meals_range:
        raise ValueError("meals_range must be non-empty")
    plans = [
        assemble_plan(
            candidates,
            target,
            k,
            max_per_recipe=max_per_recipe,
            tolerance=tolerance,
            avoid_recipe_ids=avoid_recipe_ids,
            inventory=inventory,
        )
        for k in meals_range
    ]
    return min(plans, key=lambda plan: _plan_sort_key(plan, avoid_recipe_ids))
