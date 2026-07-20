from fastapi import APIRouter, HTTPException

from app.rag.loaders import load_corpus
from app.schemas.day_plan import (
    DayPlanRequest,
    DayPlanResponse,
    ShoppingListRequest,
    ShoppingListResponse,
)
from app.schemas.recommendation import RejectedRecipe
from app.services.constraint_engine import validate_recipe
from app.services.day_planner import assemble_day_plan, assemble_plan
from app.services.procurement_service import build_shopping_list_for_plan

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
                safe_candidates, target, request.meals, max_per_recipe=request.max_per_recipe
            )
        else:
            plan = assemble_day_plan(safe_candidates, target, max_per_recipe=request.max_per_recipe)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DayPlanResponse(plan=plan, rejected_recipes=rejected)


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
