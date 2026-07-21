"""Deterministic meal-prep batch solver (roadmap item, Phase 4 item 1):
pick 2-3 recipes and scale them to N containers, each container hitting a
per-container kcal/protein target, with one consolidated shopping list (the
shopping list itself is built by `app.services.procurement_service.
build_shopping_list_for_items`, reused unmodified -- see that function and
`app.api.routes_day_planner.plan_batch`).

THE HARD SAFETY INVARIANT (do not weaken -- mirrors app.services.
day_planner's own invariant verbatim): this module operates strictly
downstream of app.services.constraint_engine.validate_recipe. It never
calls, reimplements, inspects allergen fields for, second-guesses, or
bypasses that decision -- callers (see app.api.routes_day_planner.
plan_batch) MUST pass only already-safety-cleared recipes into
`assemble_batch_plan`. This module has no knowledge of allergies, diet
type, or any other safety-relevant field; it reads macros ONLY through
`app.services.nutrition_view.trusted_per_serving`, the same sole trust
chokepoint day_planner uses -- PARTIAL, UNGROUNDED, and flagged-GROUNDED
recipes are silently dropped from the candidate pool, never trusted.

No LLM call anywhere in this file, and none should ever be added here -- an
LLM may at most phrase an ALREADY-assembled BatchPlan afterward; it may
never choose, rank, or filter the plan's contents (CLAUDE.md's core
invariant).

PROBLEM SHAPE (design consult, decided -- do not swap without a fresh
consult): "each container hitting X kcal/Y g protein" is a PER-CONTAINER
constraint, not a summed one -- every recipe contributing containers must
have its OWN per-serving macros individually within tolerance of the
target. This collapses the problem to filter-then-sort-then-take-top, NOT
combinatorial search (contrast app.services.day_planner's
enumerate-then-score, which sums a variable-size multiset of servings
against a single summed target): filter the trusted pool down to
"container-eligible" recipes (`_container_eligible`), sort by fit
(`(kcal_relative_error, protein_relative_error)`, kcal primary -- mirrors
`day_planner._plan_sort_key`), take the best `max_recipes`. No enumeration,
no new solver dependency -- this repo's only numerical deps stay
numpy/pandas.

TOLERANCE: reuses `app.services.day_planner.DEFAULT_TOLERANCE` verbatim
(+/-10% kcal, +/-15% protein -- the exact same pre-registered `B3` numbers,
imported rather than re-declared so the two modules can never silently
drift apart), applied PER CONTAINER (i.e. against each selected recipe's
own per-serving macros individually, a two-sided band on both, never a
floor) -- a stricter application than B3's summed band. Fixed before
`scripts/evaluate_batch_planner.py` was ever run; not tuned after seeing
results, even though the realistic-round bucket is expected to show lower
feasibility than B3's own eval given the harder per-serving-band
constraint against the same small trusted pool.

INGREDIENT-SHARING IS NOT A SCORED OBJECTIVE (v1, decided): recipes are
selected by macro fit alone. Whatever ingredient overlap exists among the
selected recipes shows up naturally in the consolidated shopping list; it
is never scored, ranked, or optimized for here. See docs/BACKLOG.md
("Meal-prep batch solver" section) for the pre-registered trigger to
revisit this (trusted pool >= ~200 recipes AND eligible sets routinely
exceed `max_recipes`, making overlap a real tiebreak choice).

DEGENERATE CASES (exact rules, decided by the design consult):
  - >= min_recipes eligible -> normal plan: take the best `max_recipes`
    eligible recipes, `within_tolerance=True`.
  - 1 <= eligible < min_recipes -> ALL eligible recipes are used (this is
    the "exactly 1 eligible" case from the design consult, generalized
    here to an arbitrary `min_recipes` without leaving a gap -- with the
    default `min_recipes=2` this is always exactly the 1-eligible case),
    each individually within tolerance, but `recipes_selected` is left
    below `min_recipes` so a caller can tell recipe variety wasn't
    achieved -- a real, distinct signal, not an error.
  - 0 eligible -> the single CLOSEST recipe (by
    `(kcal_relative_error, protein_relative_error)`, even though it's
    outside tolerance) fills every container, `within_tolerance=False` --
    the honest "closest we could do" result, never an empty pad.
  - Trusted pool itself empty -> `items=[]`, `within_tolerance=False`,
    `recipes_selected=0`.

WHOLE CONTAINERS ONLY: `_distribute_containers` never returns a fractional
count. `base = containers // R` (R = number of selected recipes); the
`remainder = containers % R` extra containers go ONE EACH to the
lowest-error (best-fitting, i.e. earliest in sort order) recipes first --
e.g. containers=10, R=3 -> [4, 3, 3]. Container counts across a returned
`BatchPlan.items` always sum to exactly `containers`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.batch_plan import BatchPlan, RecipeFit
from app.schemas.day_plan import PlanItem
from app.schemas.recipe import Recipe
from app.services.day_planner import DEFAULT_TOLERANCE, MacroTolerance
from app.services.nutrition_view import trusted_per_serving

# "Pick 2-3 recipes ... scale to 10 containers" (roadmap item phrasing).
DEFAULT_CONTAINERS = 10
DEFAULT_MIN_RECIPES = 2
DEFAULT_MAX_RECIPES = 3


def _relative_error(value: float, target: float) -> float:
    """Mirrors `app.services.day_planner._relative_error`'s exact semantics
    (duplicated, not imported, to keep this module self-contained and avoid
    reaching into day_planner's private surface -- day_planner.py itself is
    off-limits to modify per this task's hard constraints): abs(value -
    target) / target, except at target == 0 where the ratio is undefined:
    0.0 if value is also exactly 0 (a perfect, if degenerate, match), else
    +inf (any nonzero value misses a zero target by an unbounded relative
    amount)."""
    if target == 0:
        return 0.0 if value == 0 else float("inf")
    return abs(value - target) / target


def _dedupe_trusted(candidates: list[Recipe]) -> list[Recipe]:
    """The one place `assemble_batch_plan` reads macros before eligibility
    scoring: only recipes `trusted_per_serving` returns a real value for
    ever enter the pool. PARTIAL/UNGROUNDED/flagged-GROUNDED candidates are
    silently dropped, never padded in. De-duplicates by `recipe_id` (first
    occurrence wins), mirroring `day_planner._dedupe_trusted`."""
    seen: set[str] = set()
    pool: list[Recipe] = []
    for recipe in candidates:
        if recipe.recipe_id in seen:
            continue
        if trusted_per_serving(recipe) is None:
            continue
        seen.add(recipe.recipe_id)
        pool.append(recipe)
    return pool


def _container_eligible(
    recipe: Recipe,
    target_kcal: float,
    target_protein: float,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
) -> tuple[bool, float, float] | None:
    """Classifies one recipe against a per-container macro target, reading
    macros ONLY via `trusted_per_serving` -- the sole trust chokepoint.
    Returns `None` (an explicit "drop this recipe from consideration"
    signal, never a fabricated eligibility) when `trusted_per_serving`
    returns `None` for this recipe (PARTIAL/UNGROUNDED/flagged-GROUNDED).
    Otherwise returns `(is_eligible, kcal_relative_error,
    protein_relative_error)`, where `is_eligible` is True iff BOTH errors
    are within `tolerance`'s two-sided band (a floor is never enough on its
    own -- e.g. a recipe with 3x the target calories is NOT eligible just
    because it clears the protein target)."""
    macros = trusted_per_serving(recipe)
    if macros is None:
        return None
    kcal_error = _relative_error(macros.calories, target_kcal)
    protein_error = _relative_error(macros.protein_g, target_protein)
    is_eligible = kcal_error <= tolerance.kcal_pct and protein_error <= tolerance.protein_pct
    return is_eligible, kcal_error, protein_error


@dataclass(frozen=True)
class _Fit:
    recipe: Recipe
    is_eligible: bool
    kcal_error: float
    protein_error: float


def _fit_sort_key(fit: _Fit) -> tuple[float, float]:
    """kcal relative error is primary (mirrors `day_planner._plan_sort_key`
    and the B3 eval design), protein relative error breaks ties."""
    return (fit.kcal_error, fit.protein_error)


def _distribute_containers(containers: int, count: int) -> list[int]:
    """Whole-container distribution across `count` recipes, ASSUMED already
    sorted best-to-worst (ascending `_fit_sort_key`): every recipe gets
    `base = containers // count`; the `remainder = containers % count`
    extra containers go ONE EACH to the lowest-error (best-fitting, i.e.
    earliest-index) recipes first. Never returns a fractional count; the
    result always sums to exactly `containers`. `count` must be >= 1 --
    callers never invoke this with an empty selection (an empty trusted
    pool is handled by an early return in `assemble_batch_plan` before this
    function is ever reached)."""
    if count < 1:
        raise ValueError("count must be >= 1")
    base, remainder = divmod(containers, count)
    return [base + 1 if i < remainder else base for i in range(count)]


def assemble_batch_plan(
    candidates: list[Recipe],
    *,
    per_container_target_calories: float,
    per_container_target_protein_g: float,
    containers: int = DEFAULT_CONTAINERS,
    min_recipes: int = DEFAULT_MIN_RECIPES,
    max_recipes: int = DEFAULT_MAX_RECIPES,
    tolerance: MacroTolerance = DEFAULT_TOLERANCE,
) -> BatchPlan:
    """The one primitive for the meal-prep batch solver (design consult,
    decided). Filters the TRUSTED subset of `candidates` down to
    container-eligible recipes (`_container_eligible`), sorts by
    `_fit_sort_key`, takes the best `max_recipes`, and distributes
    `containers` whole containers across them (`_distribute_containers`).
    See this module's docstring for the exact degenerate-case rules (0 /
    1..<min_recipes / >=min_recipes eligible, and an empty trusted pool).

    Safety boundary: `candidates` MUST already be safety-cleared by
    `app.services.constraint_engine.validate_recipe` before calling this --
    this function has no allergy/diet awareness at all and will happily
    select an unsafe recipe if handed one; see
    `app.api.routes_day_planner.plan_batch` for the mandatory filtering
    step.

    Trust boundary: reads macros ONLY via
    `app.services.nutrition_view.trusted_per_serving` -- PARTIAL,
    UNGROUNDED, and flagged-GROUNDED candidates are dropped before
    eligibility is ever computed, never selected.
    """
    if containers < 1:
        raise ValueError("containers must be >= 1")
    if min_recipes < 1:
        raise ValueError("min_recipes must be >= 1")
    if max_recipes < 1:
        raise ValueError("max_recipes must be >= 1")

    pool = _dedupe_trusted(candidates)
    trusted_pool_size = len(pool)

    if trusted_pool_size == 0:
        return BatchPlan(
            items=[],
            containers=containers,
            per_container_target_calories=per_container_target_calories,
            per_container_target_protein_g=per_container_target_protein_g,
            recipes_selected=0,
            within_tolerance=False,
            trusted_pool_size=0,
            recipe_fits=[],
        )

    all_fits: list[_Fit] = []
    for recipe in pool:
        result = _container_eligible(
            recipe, per_container_target_calories, per_container_target_protein_g, tolerance
        )
        if result is None:
            # Pool is already trusted-per-serving-filtered, so this should
            # never trigger -- defensive only, never assume.
            continue
        is_eligible, kcal_error, protein_error = result
        all_fits.append(
            _Fit(recipe=recipe, is_eligible=is_eligible, kcal_error=kcal_error, protein_error=protein_error)
        )

    eligible_fits = sorted((fit for fit in all_fits if fit.is_eligible), key=_fit_sort_key)

    if len(eligible_fits) >= min_recipes:
        selected = eligible_fits[:max_recipes]
        within_tolerance = True
    elif len(eligible_fits) >= 1:
        # 1 <= eligible < min_recipes: use all of them (see module
        # docstring's degenerate-case rules) -- recipes_selected below
        # min_recipes is the "variety not achieved" signal.
        selected = eligible_fits
        within_tolerance = True
    else:
        # 0 eligible: the single closest recipe (even out of tolerance)
        # fills every container -- an honest fallback, never an empty pad.
        # all_fits is guaranteed non-empty here: trusted_pool_size > 0 and
        # every pool recipe produces a _Fit (see the defensive-only `None`
        # skip above).
        selected = [min(all_fits, key=_fit_sort_key)]
        within_tolerance = False

    if len(selected) > containers:
        # Every selected recipe must fill at least one WHOLE container
        # (PlanItem.servings is bounded >= 1, never 0) -- if there are more
        # selected recipes than containers to fill (e.g. containers=1 with
        # min_recipes=2 both eligible), keep only the best-fitting
        # `containers` of them (already sorted best-to-worst) rather than
        # handing any recipe a zero-container, fabricated-looking slot.
        selected = selected[:containers]

    counts = _distribute_containers(containers, len(selected))

    items: list[PlanItem] = []
    recipe_fits: list[RecipeFit] = []
    for fit, count in zip(selected, counts):
        macros = trusted_per_serving(fit.recipe)
        assert macros is not None  # pool is pre-filtered trusted; defensive only
        items.append(PlanItem(recipe_id=fit.recipe.recipe_id, title=fit.recipe.title, servings=count))
        recipe_fits.append(
            RecipeFit(
                recipe_id=fit.recipe.recipe_id,
                title=fit.recipe.title,
                per_serving_calories=macros.calories,
                per_serving_protein_g=macros.protein_g,
                kcal_relative_error=fit.kcal_error,
                protein_relative_error=fit.protein_error,
                container_count=count,
            )
        )

    return BatchPlan(
        items=items,
        containers=containers,
        per_container_target_calories=per_container_target_calories,
        per_container_target_protein_g=per_container_target_protein_g,
        recipes_selected=len(selected),
        within_tolerance=within_tolerance,
        trusted_pool_size=trusted_pool_size,
        recipe_fits=recipe_fits,
    )
