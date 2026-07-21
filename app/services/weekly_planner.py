"""Deterministic full weekly meal-plan assembly (roadmap Phase 4 item 2).

THIS IS A THIN COMPOSITION OF B3 (`app.services.day_planner`), NOT A NEW
SOLVER. Recipe selection is macro-only and pantry-independent: macros don't
depend on pantry state, so there is no benefit to carrying pantry-depletion
state day-to-day -- that would be dead machinery. A week is simply N
independent calls to `app.services.day_planner.assemble_day_plan` (one per
day, same target every time) plus ONE consolidated shopping-list
reconciliation across every day's `PlanItem`s (built by the caller, see
`app.api.routes_day_planner.plan_week`, via
`app.services.procurement_service.build_shopping_list_for_items` -- NOT
built in this module).

`app/services/day_planner.py` is READ-ONLY from this module's perspective:
`assemble_day_plan` is imported and called `days` times, never
reimplemented, and `DEFAULT_TOLERANCE`/`MacroTolerance` are imported from it
rather than redeclared (the established pattern `app.services.batch_planner`
already uses for `MacroTolerance`/`DEFAULT_TOLERANCE`, confirmed safe in
that module's own review) so the two modules can never silently drift apart
on the tolerance numbers.

THE HARD SAFETY INVARIANT (do not weaken -- mirrors `app.services.
day_planner`'s and `app.services.batch_planner`'s own invariant verbatim):
this module operates strictly downstream of
`app.services.constraint_engine.validate_recipe`. It never calls,
reimplements, inspects allergen fields for, second-guesses, or bypasses
that decision -- callers (see `app.api.routes_day_planner.plan_week`) MUST
pass only already-safety-cleared recipes into `assemble_week`. This module
has no knowledge of allergies, diet type, or any other safety-relevant
field. No LLM call anywhere in this file, and none should ever be added
here -- an LLM may at most phrase an ALREADY-assembled WeeklyPlan
afterward; it may never choose, rank, or filter the plan's contents
(CLAUDE.md's core invariant).

KNOWN, DELIBERATE, HONEST LIMITATION -- state loudly, do not bury (also
documented on `app.schemas.weekly_plan.WeeklyPlan`): because selection is
deterministic and pantry-independent, and the trusted pool is tiny (~15
recipes as of the A3 corpus -- re-verify the live count against
`data/processed/grounding.jsonl` / `scripts/evaluate_weekly_planner.py`'s
own printed pool size), **all `days` days will typically come out
IDENTICAL** (the same day-plan repeated). This is an honest artifact of the
corpus's current grounding coverage, not a bug -- see docs/BACKLOG.md
("Weekly meal-plan solver") for the pre-registered "day-to-day variety"
follow-up, once the trusted pool grows.

COST/BUDGET IS OUT OF SCOPE (standing human pause, "cost estimation v1"):
no pricing, no dollar figures, anywhere in this module.

PERISHABLE SEQUENCING IS DEFERRED ENTIRELY, NOT BUILT AT ALL (do not add a
partial version). `app.schemas.inventory.ConfirmedIngredient.expires_soon`
is a bare boolean with no ordering information, so it cannot support real
"use the ingredient that expires soonest first" sequencing. See
docs/BACKLOG.md for the dependency this needs before it can be built.

PANTRY UTILIZATION IS REPORTED, NEVER OPTIMIZED OR GATED. `assemble_week`
computes `WeeklyPlan.pantry_utilization` purely for display -- it never
influences which recipes are selected (selection is `assemble_day_plan`'s
macro-only decision, untouched) and it never gates `within_tolerance` on
any `DayPlan`. Never describe this metric as "maximized" or "optimized"
anywhere (code comments, docstrings, API docs, UI copy).
"""

from __future__ import annotations

from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.ingredient import scale_ingredients
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets
from app.schemas.weekly_plan import WeeklyPlan
from app.services.day_planner import (
    DEFAULT_MEALS_RANGE,
    DEFAULT_TOLERANCE,
    MacroTolerance,
    assemble_day_plan,
)
from app.services.nutrition_view import trusted_per_serving
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient
from app.utils.unit_converter import to_grams


def _trusted_pool_size(candidates: list[Recipe]) -> int:
    """The exact same trust boundary `app.services.day_planner` uses
    internally (`app.services.nutrition_view.trusted_per_serving`),
    reimplemented locally ONLY for the `trusted_pool_size` reporting field
    (mirrors `app.services.batch_planner._dedupe_trusted`'s own duplication
    of this pattern rather than reaching into `day_planner`'s private
    surface, which is off-limits to modify/import-from per this module's
    hard constraints). Real assembly always goes through
    `assemble_day_plan`'s own (re-applied) filtering -- this count is
    display-only."""
    seen: set[str] = set()
    count = 0
    for recipe in candidates:
        if recipe.recipe_id in seen:
            continue
        if trusted_per_serving(recipe) is None:
            continue
        seen.add(recipe.recipe_id)
        count += 1
    return count


def _aggregate_grams_needed(
    plan_items: list[PlanItem], recipe_lookup: dict[str, Recipe]
) -> dict[str, float | None]:
    """Combine every `PlanItem`'s scaled ingredient need into ONE grams
    total per normalized ingredient name across the WHOLE week, using the
    same `app.utils.unit_converter.to_grams` arithmetic
    `app.services.procurement_service.build_shopping_list_for_items` uses
    for its own combine-then-reconcile-once aggregation. Reimplemented here
    (not imported -- that function's internals are private to
    `procurement_service`) purely to compute the `pantry_utilization`
    *metric*, which is display-only and never feeds back into
    `procurement_service`'s own shopping-list build (that build stays a
    single separate call at the API layer -- see
    `app.api.routes_day_planner.plan_week`).

    A `None` value for a key means at least one contributor's need could
    not be resolved to grams -- the combined total for that ingredient is
    therefore unknown and must be excluded from the utilization calc
    (never silently treated as 0)."""
    grams_by_name: dict[str, float | None] = {}
    for plan_item in plan_items:
        recipe = recipe_lookup.get(plan_item.recipe_id)
        if recipe is None:
            continue
        factor = plan_item.servings / (recipe.servings or 1)
        for ingredient in scale_ingredients(recipe.ingredients, factor):
            key = normalize_ingredient(ingredient.name)
            if not key:
                continue
            grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
            if key not in grams_by_name:
                grams_by_name[key] = 0.0
            if grams is None or grams_by_name[key] is None:
                grams_by_name[key] = None
            else:
                grams_by_name[key] += grams
    return grams_by_name


def _pantry_have_grams(name: str, inventory: list[ConfirmedIngredient]) -> float | None:
    """Total grams on hand across pantry items matching `name` (already a
    normalized ingredient key), or `None` if any matched item's quantity
    can't be resolved to grams (unknown unit/density -- an incomparable
    contribution poisons the whole total, mirroring
    `procurement_service._available_grams`'s own all-or-nothing rule for
    the same reason: a partially-unknown total is not a trustworthy
    number). No matching pantry item at all is NOT the same as
    incomparable -- it is a comparable "0 g on hand"."""
    matches = [item for item in inventory if ingredient_matches(name, item.name)]
    if not matches:
        return 0.0
    total = 0.0
    for item in matches:
        grams = to_grams(item.amount, item.unit, name=item.name or name)
        if grams is None:
            return None
        total += grams
    return total


def compute_pantry_utilization(
    plan_items: list[PlanItem],
    recipe_lookup: dict[str, Recipe],
    inventory: list[ConfirmedIngredient],
) -> tuple[float, int]:
    """`(utilization, uncompared_ingredient_count)` for the pooled `plan_items`
    (typically every day's `PlanItem`s, pooled across the whole week) against
    `inventory`. `utilization` = (grams of the week's total ingredient need
    covered by the pantry) / (total grams needed), summed ONLY over
    ingredients where both the need and the pantry quantity resolve to
    grams via `to_grams` -- an ingredient where either side is `None`
    (incomparable) is excluded from BOTH the numerator and denominator and
    counted in `uncompared_ingredient_count` instead (mirrors
    `procurement_service`'s own `present_uncompared` honesty pattern: never
    silently treat an uncomparable ingredient as 0% or 100% covered). Per
    ingredient, "covered" is capped at `min(need, have)` -- surplus pantry
    stock beyond what's needed never inflates utilization past 100% for
    that ingredient. Returns `(0.0, uncompared_count)` when there is no
    comparable need at all (e.g. an empty plan, or every ingredient
    incomparable) -- never a fabricated "fully covered" claim on nothing.

    REPORTED FOR VISIBILITY ONLY -- see this module's docstring: never used
    to select, gate, or rank recipes."""
    grams_needed = _aggregate_grams_needed(plan_items, recipe_lookup)
    total_needed = 0.0
    total_covered = 0.0
    uncompared = 0
    for name, need in grams_needed.items():
        if need is None:
            uncompared += 1
            continue
        have = _pantry_have_grams(name, inventory)
        if have is None:
            uncompared += 1
            continue
        total_needed += need
        total_covered += min(need, have)
    utilization = total_covered / total_needed if total_needed > 0 else 0.0
    return utilization, uncompared


def assemble_week(
    candidates: list[Recipe],
    target: MacroTargets,
    *,
    days: int = 7,
    meals_range: tuple[int, ...] = DEFAULT_MEALS_RANGE,
    max_per_recipe: int = 2,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
    inventory: list[ConfirmedIngredient] | None = None,
) -> WeeklyPlan:
    """The one primitive for the full weekly meal-plan solver (design
    consult, decided -- see this module's docstring). Calls
    `app.services.day_planner.assemble_day_plan` exactly `days` times, same
    `candidates`/`target`/`meals_range`/`max_per_recipe`/`tolerance` every
    time (day_planner.py is never modified or reimplemented), and collects
    the results into `WeeklyPlan.days`.

    Also computes the reported-only `pantry_utilization` /
    `uncompared_ingredient_count` metric (`compute_pantry_utilization`)
    over every day's `PlanItem`s pooled together against `inventory`
    (`[]` when omitted -- 0.0 utilization, since there is nothing to
    reconcile against). NOTE: this is a SEPARATE, display-only computation
    from the week's actual shopping list -- the shopping list itself MUST
    be built by the caller via exactly one call to
    `app.services.procurement_service.build_shopping_list_for_items` over
    the same pooled `PlanItem`s (see `app.api.routes_day_planner.plan_week`
    and this module's docstring for why a per-day-then-merge composition
    would double-count pantry availability, the exact B4 bug class).

    Safety boundary: `candidates` MUST already be safety-cleared by
    `app.services.constraint_engine.validate_recipe` before calling this --
    this function has no allergy/diet awareness at all and will happily
    select an unsafe recipe if handed one; see
    `app.api.routes_day_planner.plan_week` for the mandatory filtering
    step.
    """
    if days < 1:
        raise ValueError("days must be >= 1")

    day_plans: list[DayPlan] = [
        assemble_day_plan(
            candidates,
            target,
            meals_range=meals_range,
            max_per_recipe=max_per_recipe,
            tolerance=tolerance,
        )
        for _ in range(days)
    ]

    recipe_lookup = {recipe.recipe_id: recipe for recipe in candidates}
    pooled_items: list[PlanItem] = [item for day_plan in day_plans for item in day_plan.items]
    utilization, uncompared = compute_pantry_utilization(pooled_items, recipe_lookup, inventory or [])

    return WeeklyPlan(
        days=day_plans,
        pantry_utilization=utilization,
        uncompared_ingredient_count=uncompared,
        trusted_pool_size=_trusted_pool_size(candidates),
    )
