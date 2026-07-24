"""Public, share-safe schemas for roadmap item "Shareable plan URLs" (Phase
4 item 4, docs/ROADMAP.md) -- the server-side FIELD-LEVEL ALLOWLIST that
keeps a private field (`Recipe.owner_user_id` above all) from ever leaking
into a public, unauthenticated share link.

THE LOAD-BEARING SAFETY PROPERTY OF THIS MODULE: every `Public*` schema
below lists ONLY the fields that are safe to hand to an anonymous caller who
has nothing but a share id. `app.services.share_service`'s mapping
functions build these objects field-by-field from the source object -- they
never `model_dump()`/persist/echo a client-supplied `Recipe`/`DayPlan`/
`BatchPlan`/`WeeklyPlan` verbatim. See that module's docstring for the full
threat model.

No LLM anywhere on this path -- this module imports nothing from
`app.services.model_provider` or any other model-provider integration, and
`tests/test_share_no_llm_import.py` asserts that statically.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.batch_plan import BatchPlan, RecipeFit
from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import RecipeNutrition
from app.schemas.recipe import Recipe
from app.schemas.shopping import ShoppingItem
from app.schemas.weekly_plan import WeeklyPlan

PlanType = Literal["recipe", "day", "batch", "week", "shopping_list"]


class PublicRecipe(BaseModel):
    """Share-safe projection of `app.schemas.recipe.Recipe`.

    Deliberately excludes (compare against the current `Recipe` field list
    in `app/schemas/recipe.py`): `owner_user_id` (the sharer's session
    identity -- THE headline leak this feature exists to prevent),
    `is_user_saved`, `image_path` (a server-local filesystem path),
    `is_active`, `restored_from_quarantine` (an internal display flag), and
    the SELF-REPORTED TAG MACROS `calories`/`protein_g`/`carbs_g`/`fat_g`/
    `fiber_g` (per `Recipe`'s own docstring, nothing should trust these
    directly -- only the grounded `nutrition` field is presentable).
    """

    recipe_id: str
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    diet_tags: list[str] = Field(default_factory=list)
    cook_time_min: int | None = None
    nutrition: RecipeNutrition | None = None
    description: str | None = None
    difficulty: str | None = None
    servings: int | None = None
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    substitution_note: str | None = None


class PublicDayPlan(BaseModel):
    """Share-safe projection of `app.schemas.day_plan.DayPlan`.

    Excludes `trusted_pool_size` (leaks how many corpus recipes were
    available to the sharer, not a property of the plan itself).
    """

    items: list[PlanItem] = Field(default_factory=list)
    meals_planned: int = Field(ge=0)

    total_calories: float = Field(ge=0)
    total_protein_g: float = Field(ge=0)
    total_carbs_g: float = Field(ge=0)
    total_fat_g: float = Field(ge=0)
    total_fiber_g: float = Field(ge=0)

    target_calories: float
    target_protein_g: float

    calories_relative_error: float = Field(ge=0)
    protein_relative_error: float = Field(ge=0)
    carbs_relative_error: float | None = None
    fat_relative_error: float | None = None
    fiber_relative_error: float | None = None

    within_tolerance: bool


class PublicBatchPlan(BaseModel):
    """Share-safe projection of `app.schemas.batch_plan.BatchPlan`.

    Excludes `trusted_pool_size` (same reasoning as `PublicDayPlan`).
    """

    items: list[PlanItem] = Field(default_factory=list)
    containers: int = Field(ge=1)
    per_container_target_calories: float = Field(ge=0)
    per_container_target_protein_g: float = Field(ge=0)
    recipes_selected: int = Field(ge=0)
    within_tolerance: bool
    recipe_fits: list[RecipeFit] = Field(default_factory=list)


class PublicWeeklyPlan(BaseModel):
    """Share-safe projection of `app.schemas.weekly_plan.WeeklyPlan`.

    Excludes `trusted_pool_size` (same reasoning as `PublicDayPlan`) and
    `pantry_utilization`/`uncompared_ingredient_count` (both are
    pantry-derived and would leak "here's what's in the sharer's kitchen"
    to an anonymous viewer).
    """

    days: list[PublicDayPlan] = Field(default_factory=list)


# `ShoppingItem` (app/schemas/shopping.py) is `{name, quantity, amount, unit,
# reason}` -- zero PII, no owner-identity field, nothing to strip. It is
# reused verbatim (not re-declared field-by-field like the four Public*
# models above) because it is already the first genuinely
# field-for-field-safe payload in this set; the bare list matches the shape
# `app.services.share_service.build_shopping_list_for_items`/
# `merge_shopping_lists` already produce and already the shape
# `ShoppingListResponse.items` sends over the wire elsewhere in the API, so
# no new wrapper object is introduced. Named as a type alias (not a
# `BaseModel`) purely so this module's naming convention
# (`Public<PlanType>`) still documents, at a glance, that a *future* field
# added to `ShoppingItem` gets the same allowlist scrutiny this module's
# docstring mandates for every other Public* type -- see
# `shopping_list_to_public` in `app.services.share_service`.
PublicShoppingList = list[ShoppingItem]


# ---------------------------------------------------------------------------
# Wire contracts for POST /share and GET /share/{id}.
# ---------------------------------------------------------------------------


class ShareCreateRequest(BaseModel):
    """Body for POST /share.

    `plan_type` selects exactly one of the five optional fields below --
    the matching object the (authenticated) client already holds in its own
    UI state. This is intentionally NOT the wire-level shape that gets
    persisted: `app.services.share_service.create_share` maps whichever
    field is populated through the server-side allowlist functions above
    before anything is written to `SharedPlan.content` -- the client object
    is read from, never echoed or persisted verbatim (see that module's
    docstring for why).
    """

    plan_type: PlanType
    recipe: Recipe | None = None
    day_plan: DayPlan | None = None
    batch_plan: BatchPlan | None = None
    weekly_plan: WeeklyPlan | None = None
    shopping_list: list[ShoppingItem] | None = None

    @model_validator(mode="after")
    def _exactly_one_matching_payload(self) -> "ShareCreateRequest":
        by_type: dict[PlanType, object | None] = {
            "recipe": self.recipe,
            "day": self.day_plan,
            "batch": self.batch_plan,
            "week": self.weekly_plan,
            "shopping_list": self.shopping_list,
        }
        expected_field = {
            "recipe": "recipe",
            "day": "day_plan",
            "batch": "batch_plan",
            "week": "weekly_plan",
            "shopping_list": "shopping_list",
        }[self.plan_type]
        if by_type[self.plan_type] is None:
            raise ValueError(
                f"plan_type={self.plan_type!r} requires the {expected_field!r} field"
            )
        others = {key: value for key, value in by_type.items() if key != self.plan_type}
        populated_others = [key for key, value in others.items() if value is not None]
        if populated_others:
            raise ValueError(
                f"plan_type={self.plan_type!r} but also received payload for "
                f"{populated_others!r} -- send exactly one plan payload matching plan_type"
            )
        return self


class ShareCreateResponse(BaseModel):
    """Response for POST /share. Deliberately just the opaque id -- no
    hardcoded public hostname (see app.api.routes_share.create_share);
    the frontend composes the full share URL itself."""

    share_id: str


class SharedPlanView(BaseModel):
    """Response for GET /share/{id} -- the ONLY thing an anonymous caller
    ever receives. Never the ORM row, never `owner_user_id`, never any field
    not declared here.
    """

    plan_type: PlanType
    content: PublicRecipe | PublicDayPlan | PublicBatchPlan | PublicWeeklyPlan | PublicShoppingList
    # Non-optional by design (Q6 of this feature's design consult) -- always
    # populated from app.services.share_service.SHARE_DISCLAIMER, never
    # left to the frontend to add or omit.
    disclaimer: str
