from fastapi import APIRouter, HTTPException

from app.rag.loaders import load_corpus
from app.schemas.batch_plan import BatchPlanRequest, BatchPlanResponse
from app.schemas.day_plan import (
    DayPlanRequest,
    DayPlanResponse,
    ShoppingListForItemsRequest,
    ShoppingListRequest,
    ShoppingListResponse,
)
from app.schemas.recommendation import RejectedRecipe
from app.schemas.weekly_plan import WeeklyPlanRequest, WeeklyPlanResponse
from app.services.batch_planner import assemble_batch_plan
from app.services.constraint_engine import validate_recipe
from app.services.day_planner import assemble_day_plan, assemble_plan
from app.services.procurement_service import build_shopping_list_for_items, build_shopping_list_for_plan
from app.services.weekly_planner import assemble_week

router = APIRouter(prefix="/plan", tags=["day-planner"])


@router.post("/day", response_model=DayPlanResponse)
def plan_day(request: DayPlanRequest) -> DayPlanResponse:
    """B3: macro-targeted day-plan assembly.

    SAFETY (mandatory, verifiable): every recipe in the corpus is run
    through `app.services.constraint_engine.validate_recipe` -- the exact
    same deterministic check `app.graph.nodes.safety_filter_node` uses
    (app/graph/nodes.py:172-200) -- BEFORE `app.services.day_planner` ever
    sees it. Only the survivors (`safe_candidates`) are passed into
    `assemble_plan`/`assemble_day_plan`; rejected recipes are reported back
    (mirroring `safety_filter_node`'s own rejected_recipes bookkeeping) but
    never reach the planner. This is the sole point in this file where
    safety is decided, and it happens purely in deterministic code -- no LLM
    call anywhere on this path.

    `request.inventory` (2026-07-22 pantry-tiebreak follow-up) is forwarded
    to `assemble_plan`/`assemble_day_plan` as `inventory=` -- this endpoint
    only ever exercises the pantry-coverage tiebreak (variety is a
    structural no-op here; there is no "prior day" for a single day-plan
    request -- see `app.services.day_planner`'s module docstring). It
    never changes which recipes are safety-cleared above, and never
    weakens the macro-fit primary sort.
    """
    all_recipes = load_corpus()
    safe_candidates = []
    rejected: list[RejectedRecipe] = []
    for recipe in all_recipes:
        result = validate_recipe(recipe, request.user_profile)
        if result.is_valid:
            safe_candidates.append(recipe)
        else:
            rejected.append(
                RejectedRecipe(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    reason=result.rejection_reason or "Rejected by hard constraint",
                )
            )

    target = request.user_profile.macro_targets
    if target.calories is None or target.protein_g is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "macro_targets.calories and macro_targets.protein_g are both "
                "required to assemble a day plan (the +/-10%/+/-15% "
                "tolerance gate is undefined without them)."
            ),
        )

    try:
        if request.meals is not None:
            plan = assemble_plan(
                safe_candidates,
                target,
                request.meals,
                max_per_recipe=request.max_per_recipe,
                inventory=request.inventory,
            )
        else:
            plan = assemble_day_plan(
                safe_candidates,
                target,
                max_per_recipe=request.max_per_recipe,
                inventory=request.inventory,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DayPlanResponse(plan=plan, rejected_recipes=rejected)


@router.post("/batch", response_model=BatchPlanResponse)
def plan_batch(request: BatchPlanRequest) -> BatchPlanResponse:
    """Phase 4 item 1: meal-prep batch solver -- pick 2-3 recipes, scale to
    N whole containers, each container individually hitting a per-container
    kcal/protein target, with one consolidated shopping list.

    SAFETY (mandatory, verifiable, identical pattern to `plan_day` above):
    every recipe in the corpus is run through
    `app.services.constraint_engine.validate_recipe` BEFORE
    `app.services.batch_planner` ever sees it. Only the survivors
    (`safe_candidates`) are passed into `assemble_batch_plan`; rejected
    recipes are reported back in `rejected_recipes` but never reach the
    planner. This is the sole point in this file where safety is decided
    for this endpoint, and it happens purely in deterministic code -- no
    LLM call anywhere on this path.

    The consolidated shopping list is built via
    `app.services.procurement_service.build_shopping_list_for_items`
    against the assembled `plan.items` and `request.inventory` -- the same
    combine-then-reconcile-once logic `plan_shopping_list` uses for a
    `DayPlan`, reused unmodified rather than reimplemented (see that
    function's docstring for the double-counting bug it avoids).
    """
    all_recipes = load_corpus()
    safe_candidates = []
    rejected: list[RejectedRecipe] = []
    for recipe in all_recipes:
        result = validate_recipe(recipe, request.user_profile)
        if result.is_valid:
            safe_candidates.append(recipe)
        else:
            rejected.append(
                RejectedRecipe(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    reason=result.rejection_reason or "Rejected by hard constraint",
                )
            )

    try:
        plan = assemble_batch_plan(
            safe_candidates,
            per_container_target_calories=request.per_container_target_calories,
            per_container_target_protein_g=request.per_container_target_protein_g,
            containers=request.containers,
            min_recipes=request.min_recipes,
            max_recipes=request.max_recipes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    recipe_lookup = {
        recipe.recipe_id: recipe
        for recipe in safe_candidates
        if recipe.recipe_id in {item.recipe_id for item in plan.items}
    }
    shopping_list = build_shopping_list_for_items(plan.items, recipe_lookup, request.inventory)

    return BatchPlanResponse(plan=plan, rejected_recipes=rejected, shopping_list=shopping_list)


@router.post("/week", response_model=WeeklyPlanResponse)
def plan_week(request: WeeklyPlanRequest) -> WeeklyPlanResponse:
    """Phase 4 item 2: full weekly meal-plan solver -- a THIN COMPOSITION of
    B3 (`app.services.day_planner`), NOT a new solver. `request.days`
    independent calls to `assemble_day_plan` (same target every time, since
    macro selection is pantry-independent -- see
    `app.services.weekly_planner`'s module docstring), plus ONE consolidated
    shopping-list reconciliation across every day's `PlanItem`s pooled
    together.

    SAFETY (mandatory, verifiable, identical pattern to `plan_day`/
    `plan_batch` above): every recipe in the corpus is run through
    `app.services.constraint_engine.validate_recipe` BEFORE
    `app.services.weekly_planner` ever sees it. Only the survivors
    (`safe_candidates`) are passed into `assemble_week`; rejected recipes
    are reported back in `rejected_recipes` but never reach the planner.
    This is the sole point in this file where safety is decided for this
    endpoint, and it happens purely in deterministic code -- no LLM call
    anywhere on this path.

    THE SINGLE MOST CORRECTNESS-CRITICAL STEP: the consolidated shopping
    list is built by exactly ONE call to
    `app.services.procurement_service.build_shopping_list_for_items`, over
    every day's `PlanItem`s pooled into one flat list, with
    `request.inventory` reconciled EXACTLY ONCE -- never a naive
    per-day-then-merge composition, which would reintroduce the exact B4
    double-counting bug class (two days each individually "satisfied" by
    the same undepleted pantry, both shortfalls artificially zeroed). See
    `build_shopping_list_for_items`'s own docstring for the full
    explanation.
    """
    all_recipes = load_corpus()
    safe_candidates = []
    rejected: list[RejectedRecipe] = []
    for recipe in all_recipes:
        result = validate_recipe(recipe, request.user_profile)
        if result.is_valid:
            safe_candidates.append(recipe)
        else:
            rejected.append(
                RejectedRecipe(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    reason=result.rejection_reason or "Rejected by hard constraint",
                )
            )

    target = request.user_profile.macro_targets
    if target.calories is None or target.protein_g is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "macro_targets.calories and macro_targets.protein_g are both "
                "required to assemble a weekly plan (the +/-10%/+/-15% "
                "tolerance gate is undefined without them)."
            ),
        )

    try:
        plan = assemble_week(
            safe_candidates,
            target,
            days=request.days,
            max_per_recipe=request.max_per_recipe,
            inventory=request.inventory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    all_plan_items = [item for day_plan in plan.days for item in day_plan.items]
    recipe_lookup = {
        recipe.recipe_id: recipe
        for recipe in safe_candidates
        if recipe.recipe_id in {item.recipe_id for item in all_plan_items}
    }
    shopping_list = build_shopping_list_for_items(all_plan_items, recipe_lookup, request.inventory)

    return WeeklyPlanResponse(plan=plan, rejected_recipes=rejected, shopping_list=shopping_list)


@router.post("/shopping-list", response_model=ShoppingListResponse)
def plan_shopping_list(request: ShoppingListRequest) -> ShoppingListResponse:
    """B4: shopping-list aggregation across an already-assembled DayPlan.

    NOT a safety endpoint: `request.plan` was already safety-cleared by
    POST /plan/day (every recipe_id in `plan.items` passed
    constraint_engine.validate_recipe there); this endpoint does pure
    quantity arithmetic (app.services.procurement_service.
    build_shopping_list_for_plan) against the full corpus looked up by id,
    and makes no allergy/diet decision of its own -- see that function's
    docstring for the servings-scaling and merge logic.
    """
    all_recipes = load_corpus()
    recipe_lookup = {
        recipe.recipe_id: recipe
        for recipe in all_recipes
        if recipe.recipe_id in {item.recipe_id for item in request.plan.items}
    }
    shopping_list = build_shopping_list_for_plan(request.plan, recipe_lookup, request.inventory)
    return ShoppingListResponse(shopping_list=shopping_list)


@router.post("/shopping-list-for-items", response_model=ShoppingListResponse)
def plan_shopping_list_for_items(request: ShoppingListForItemsRequest) -> ShoppingListResponse:
    """Frontend recipe search/plan-builder follow-up: shopping-list
    aggregation across a caller-supplied `list[PlanItem]` that did NOT come
    from `assemble_plan`/`assemble_day_plan` (e.g. a manually-curated
    selection assembled client-side from `POST /recipes/search` results --
    see `app.schemas.day_plan.ShoppingListForItemsRequest`'s docstring).

    NOT a safety endpoint, identical posture to `plan_shopping_list` above:
    every `recipe_id` in `request.items` was already safety-cleared when the
    user found it via a safety-filtering search/recommend endpoint, so this
    endpoint makes no new safety/allergy/diet decision -- it only does pure
    quantity arithmetic (`app.services.procurement_service.
    build_shopping_list_for_items`, the exact same aggregate-then-reconcile-
    once call `plan_batch`/`plan_week` already use for their own
    `list[PlanItem]`) against the full corpus looked up by id. A
    `recipe_id` absent from the corpus is silently skipped by
    `build_shopping_list_for_items` (never fabricated), same as every other
    caller of that function.
    """
    all_recipes = load_corpus()
    recipe_lookup = {
        recipe.recipe_id: recipe
        for recipe in all_recipes
        if recipe.recipe_id in {item.recipe_id for item in request.items}
    }
    shopping_list = build_shopping_list_for_items(request.items, recipe_lookup, request.inventory)
    return ShoppingListResponse(shopping_list=shopping_list)
