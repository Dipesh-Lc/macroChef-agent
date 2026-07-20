from pydantic import BaseModel, Field

from app.schemas.recommendation import RejectedRecipe
from app.schemas.user import UserProfile


class PlanItem(BaseModel):
    """One recipe's contribution to a DayPlan: how many whole servings of it
    were selected. v1 is whole-servings-only (roadmap item B3) -- no
    fractional/continuous portion scaling, which would make the +/-10%/
    +/-15% tolerance trivially satisfiable and gut the eval's meaning (see
    app.services.day_planner's module docstring and docs/BACKLOG.md for the
    continuous-scaling follow-up, which could reuse
    app.schemas.ingredient.scale_ingredients from roadmap item B2)."""

    recipe_id: str
    title: str
    servings: int = Field(ge=1)


class DayPlan(BaseModel):
    """Result of app.services.day_planner.assemble_plan (or its
    assemble_day_plan / assemble_remaining_meal thin wrappers).

    `items` lists the selected recipes and how many whole servings of each
    (multiplicity capped by `max_per_recipe` at assembly time). `meals_planned`
    is the actual number of recipe-servings assembled (== the requested K
    when a feasible combo existed; 0 when the enumerator could not build ANY
    combo of the requested size -- e.g. an empty trusted pool, or K exceeding
    `max_per_recipe * trusted_pool_size` -- never a padded or partial guess).

    `within_tolerance` is the SOLE fit gate: True iff summed kcal is within
    the pre-registered +/-10% of target calories AND summed protein is
    within +/-15% of target protein_g (see
    app.services.day_planner.MacroTolerance). carbs/fat/fiber relative
    errors are reported for visibility only and never affect this flag (a
    deliberate v1 scope decision from the B3 design consult).

    When nothing fits, the CLOSEST plan is still returned with
    within_tolerance=False -- callers must check this flag explicitly rather
    than assume a non-empty `items` means the target was met.
    """

    items: list[PlanItem] = Field(default_factory=list)
    meals_planned: int = Field(ge=0)
    trusted_pool_size: int = Field(ge=0)

    total_calories: float = Field(ge=0)
    total_protein_g: float = Field(ge=0)
    total_carbs_g: float = Field(ge=0)
    total_fat_g: float = Field(ge=0)
    total_fiber_g: float = Field(ge=0)

    target_calories: float
    target_protein_g: float

    calories_relative_error: float = Field(ge=0)
    protein_relative_error: float = Field(ge=0)
    # Secondary macros: reported, never gating (see class docstring). None
    # when the target itself didn't specify that macro.
    carbs_relative_error: float | None = None
    fat_relative_error: float | None = None
    fiber_relative_error: float | None = None

    within_tolerance: bool


class DayPlanRequest(BaseModel):
    """Wire contract for POST /plan/day. `user_profile.macro_targets` is
    used directly as the assembly target -- for "remaining macros" mode the
    caller computes the remainder client-side (target minus what's already
    been eaten today) and puts it here; this endpoint holds no eaten-today
    state itself (see app.services.day_planner.assemble_remaining_meal's
    docstring).

    No `candidate_recipe_ids` field, deliberately: the endpoint always
    starts from the full corpus and applies
    app.services.constraint_engine.validate_recipe itself (see
    app.api.routes_day_planner.plan_day) -- letting a client hand in a
    pre-filtered candidate list would open a second, client-controlled path
    around that mandatory safety filter.
    """

    user_profile: UserProfile
    # None (default) -> "day plan" mode: sweep
    # app.services.day_planner.DEFAULT_MEALS_RANGE and return the globally
    # best result. An explicit int -> calls assemble_plan(meals=meals)
    # directly for that exact K -- 1 is "remaining macros" mode; any other
    # value is a fixed-K day plan.
    meals: int | None = Field(default=None, ge=0, le=8)
    max_per_recipe: int = Field(default=2, ge=1, le=4)


class DayPlanResponse(BaseModel):
    plan: DayPlan
    # Every candidate constraint_engine.validate_recipe rejected before
    # assemble_plan/assemble_day_plan ever saw it -- mirrors
    # RecommendationResponse.rejected_recipes (app.schemas.recommendation)
    # so a caller (and a reviewer) can verify the safety filter actually ran.
    rejected_recipes: list[RejectedRecipe] = Field(default_factory=list)
