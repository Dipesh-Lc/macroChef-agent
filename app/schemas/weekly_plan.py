from pydantic import BaseModel, Field

from app.schemas.day_plan import DayPlan
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import RejectedRecipe
from app.schemas.shopping import ShoppingItem
from app.schemas.user import UserProfile


class WeeklyPlan(BaseModel):
    """Result of `app.services.weekly_planner.assemble_week` (roadmap item,
    Phase 4 item 2: full weekly meal-plan solver).

    THIS IS A THIN COMPOSITION OF B3 (`app.services.day_planner`), not a new
    solver: `days` is exactly `app.services.day_planner.assemble_day_plan`
    called once per day, same target every time -- see that module's own
    docstring for the algorithm, tolerance, and trust boundary, all reused
    unchanged.

    KNOWN, DELIBERATE, HONEST LIMITATION -- state loudly, do not bury:
    because recipe selection is macro-only and pantry-independent (macros
    don't depend on pantry state, so there is no day-to-day pantry-depletion
    state carried between calls), and the trusted pool is tiny (~15 recipes
    as of the A3 corpus -- see `app.services.day_planner`'s "CRUX FINDING"),
    every one of `days` calls to `assemble_day_plan` receives the exact same
    candidates and the exact same target, and is therefore fully
    deterministic. **All `days` entries in `WeeklyPlan.days` will typically
    come out IDENTICAL** (the same day-plan repeated `days` times). This is
    an honest artifact of the corpus's current grounding coverage, not a
    bug in this module -- see docs/BACKLOG.md ("Weekly meal-plan solver")
    for the pre-registered "day-to-day variety" follow-up.

    `pantry_utilization` is REPORTED FOR VISIBILITY ONLY -- it is never
    optimized, maximized, or used to gate/select which recipes are chosen.
    It is the fraction of the week's total (quantity-comparable) ingredient
    need that the supplied pantry (`ConfirmedIngredient` inventory) covers,
    computed with the same `app.utils.unit_converter.to_grams` arithmetic
    `app.services.procurement_service` uses. Ingredients whose need or
    pantry quantity can't be resolved to grams (`to_grams` returns `None`)
    are excluded from BOTH the numerator and denominator -- never silently
    treated as 0% or 100% covered -- and counted separately in
    `uncompared_ingredient_count` (mirrors `procurement_service`'s own
    `present_uncompared` honesty pattern).
    """

    days: list[DayPlan] = Field(default_factory=list)
    pantry_utilization: float = Field(ge=0, le=1)
    uncompared_ingredient_count: int = Field(ge=0)
    trusted_pool_size: int = Field(ge=0)


class WeeklyPlanRequest(BaseModel):
    """Wire contract for POST /plan/week.

    `user_profile.macro_targets` is used as the SAME target for every day
    of the week (mirrors `DayPlanRequest`'s own use of
    `user_profile.macro_targets` -- see `app/schemas/day_plan.py`).

    No `candidate_recipe_ids` field, deliberately -- same reasoning as
    `DayPlanRequest`/`BatchPlanRequest`: the endpoint always starts from the
    full corpus and applies `app.services.constraint_engine.validate_recipe`
    itself (see `app.api.routes_day_planner.plan_week`) -- letting a client
    hand in a pre-filtered candidate list would open a second,
    client-controlled path around that mandatory safety filter.

    `inventory` mirrors `BatchPlanRequest.inventory` in shape: this endpoint
    builds the week's ONE CONSOLIDATED shopping list itself (via
    `app.services.procurement_service.build_shopping_list_for_items`, pooling
    every day's `PlanItem`s together) as part of the same request/response
    round trip, and also feeds `pantry_utilization`. Defaults to empty (no
    pantry reconciliation, full quantities listed, 0.0 utilization) when
    omitted.
    """

    user_profile: UserProfile
    days: int = Field(default=7, ge=1, le=14)
    max_per_recipe: int = Field(default=2, ge=1, le=4)
    inventory: list[ConfirmedIngredient] = Field(default_factory=list)


class WeeklyPlanResponse(BaseModel):
    plan: WeeklyPlan
    # Every candidate constraint_engine.validate_recipe rejected before
    # assemble_week ever saw it -- mirrors DayPlanResponse/BatchPlanResponse
    # so a caller (and a reviewer) can verify the safety filter actually ran.
    rejected_recipes: list[RejectedRecipe] = Field(default_factory=list)
    # The week's ONE CONSOLIDATED shopping list, at the RESPONSE level
    # (exactly like BatchPlanResponse.shopping_list -- NOT nested inside
    # WeeklyPlan). Built by exactly ONE call to
    # app.services.procurement_service.build_shopping_list_for_items over
    # every day's PlanItems pooled together, reconciled against
    # request.inventory exactly once -- see app.services.weekly_planner's
    # module docstring for why a per-day-then-merge composition would
    # reintroduce the B4 double-counting bug class.
    shopping_list: list[ShoppingItem] = Field(default_factory=list)
