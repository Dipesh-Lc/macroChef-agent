from pydantic import BaseModel, Field

from app.schemas.day_plan import PlanItem
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import RejectedRecipe
from app.schemas.shopping import ShoppingItem
from app.schemas.user import UserProfile


class RecipeFit(BaseModel):
    """One selected recipe's fit against the batch plan's per-container
    macro target -- the public-facing projection of
    `app.services.batch_planner._container_eligible` for a recipe that
    ended up in `BatchPlan.items`. Display/debugging detail, not a second
    source of truth: `recipe_id` and `container_count` always line up 1:1
    with `BatchPlan.items` (same recipe_id, `container_count ==
    PlanItem.servings`) for the same `BatchPlan`."""

    recipe_id: str
    title: str
    per_serving_calories: float = Field(ge=0)
    per_serving_protein_g: float = Field(ge=0)
    kcal_relative_error: float = Field(ge=0)
    protein_relative_error: float = Field(ge=0)
    container_count: int = Field(ge=0)


class BatchPlan(BaseModel):
    """Result of `app.services.batch_planner.assemble_batch_plan` (roadmap
    item: meal-prep batch solver, Phase 4 item 1). Deliberately NOT a
    repurposed `DayPlan` -- `DayPlan`'s `total_*`/`target_*` fields encode a
    SUMMED-vs-summed target (B3 semantics: many servings summed against one
    day-level target), while a `BatchPlan`'s fit is PER CONTAINER: every
    selected recipe's OWN per-serving macros must individually sit within
    tolerance of the per-container target. Jamming that into `DayPlan`
    would misrepresent the numbers, so this is a new, independent schema.
    See `app.services.batch_planner`'s module docstring for the full
    algorithm and the exact degenerate-case rules (0 eligible / 1 up to
    `min_recipes` eligible / >= `min_recipes` eligible, and an empty
    trusted pool).

    `items` lists the selected recipes and how many whole containers each
    fills (`PlanItem.servings` is reused AS the container count for that
    recipe) -- container counts across `items` always sum to exactly
    `containers`, never a fractional split. `recipe_fits` carries the same
    selection's per-recipe fit detail (relative errors, per-serving
    macros) for display/debugging, aligned 1:1 with `items`.

    `within_tolerance` is True iff every selected recipe was individually
    container-eligible (its own per-serving kcal AND protein each within
    the pre-registered +/-10%/+/-15% band of the per-container target,
    reused verbatim from `app.services.day_planner.DEFAULT_TOLERANCE`) --
    False only in the "0 eligible recipes, closest recipe used as an
    honest fallback" case (see module docstring); callers must check this
    flag explicitly rather than assume a non-empty `items` means the
    target was met.

    `recipes_selected` can be LESS than the caller's requested
    `min_recipes` when fewer than `min_recipes` trusted recipes were
    container-eligible -- a real, distinct "recipe variety not achieved"
    signal (still `within_tolerance=True` per-container in that case), not
    an error condition; callers must check this explicitly too.
    """

    items: list[PlanItem] = Field(default_factory=list)
    containers: int = Field(ge=1)
    per_container_target_calories: float = Field(ge=0)
    per_container_target_protein_g: float = Field(ge=0)
    recipes_selected: int = Field(ge=0)
    within_tolerance: bool
    trusted_pool_size: int = Field(ge=0)
    recipe_fits: list[RecipeFit] = Field(default_factory=list)


class BatchPlanRequest(BaseModel):
    """Wire contract for POST /plan/batch (meal-prep batch solver).

    No `candidate_recipe_ids` field, deliberately -- same reasoning as
    `DayPlanRequest` (`app/schemas/day_plan.py`): the endpoint always
    starts from the full corpus and applies
    `app.services.constraint_engine.validate_recipe` itself (see
    `app.api.routes_day_planner.plan_batch`) -- letting a client hand in a
    pre-filtered candidate list would open a second, client-controlled
    path around that mandatory safety filter.

    `inventory` mirrors `ShoppingListRequest.inventory`
    (`app/schemas/day_plan.py`) in shape, but is consumed differently: this
    endpoint builds the batch plan's ONE CONSOLIDATED shopping list itself
    (via `app.services.procurement_service.build_shopping_list_for_items`)
    as part of the same request/response round trip, rather than requiring
    a second call through POST /plan/shopping-list (which only accepts a
    `DayPlan`, not a `BatchPlan`) -- see `app.api.routes_day_planner.
    plan_batch`. Defaults to empty (no pantry reconciliation, full
    quantities listed) when omitted.
    """

    user_profile: UserProfile
    per_container_target_calories: float = Field(gt=0)
    per_container_target_protein_g: float = Field(gt=0)
    containers: int = Field(default=10, ge=1, le=30)
    min_recipes: int = Field(default=2, ge=1, le=5)
    max_recipes: int = Field(default=3, ge=1, le=5)
    inventory: list[ConfirmedIngredient] = Field(default_factory=list)


class BatchPlanResponse(BaseModel):
    plan: BatchPlan
    # Every candidate constraint_engine.validate_recipe rejected before
    # assemble_batch_plan ever saw it -- mirrors DayPlanResponse.
    # rejected_recipes so a caller (and a reviewer) can verify the safety
    # filter actually ran.
    rejected_recipes: list[RejectedRecipe] = Field(default_factory=list)
    # The batch plan's ONE CONSOLIDATED shopping list (the roadmap item's
    # own phrasing), built via
    # app.services.procurement_service.build_shopping_list_for_items
    # against `plan.items` -- combine every selected recipe's scaled need
    # into one consolidated per-ingredient total FIRST, then reconcile
    # against `request.inventory` exactly once. Never a naive per-recipe
    # merge (see that function's docstring for why that double-counts
    # pantry availability).
    shopping_list: list[ShoppingItem] = Field(default_factory=list)
