from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.ingredient import Ingredient

# The quantity/unit data model (item 1.2) landed and made `Ingredient` the one
# canonical `{name, amount, unit}` shape. `NutritionIngredient` is kept as an
# alias so existing grounding callers/tests keep working without duplicating the
# model.
NutritionIngredient = Ingredient


class FoodMacros(BaseModel):
    """Macro nutrients per 100g of a food, as reported by USDA FDC."""

    calories: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    fiber_g: float = Field(ge=0)


class FoodMatch(BaseModel):
    """A single FDC food matched for a normalized ingredient query."""

    fdc_id: int
    description: str
    data_type: str
    macros: FoodMacros
    query: str


class GroundingStatus(str, Enum):
    """How much of a recipe's macros were derived from real ingredient data.

    This is deliberately a first-class, explicit result rather than a bare
    number or `None` — a recipe with no grounded ingredients must never be
    mistaken for one that is genuinely low-calorie. Callers should branch on
    this before trusting `RecipeNutrition.total` / `per_serving`.
    """

    GROUNDED = "grounded"
    PARTIAL = "partial"
    UNGROUNDED = "ungrounded"


class IngredientContribution(BaseModel):
    """The grounding outcome for a single recipe ingredient."""

    name: str
    grams: float | None = None
    match: FoodMatch | None = None
    macros: FoodMacros | None = None
    grounded: bool = False


class RecipeNutrition(BaseModel):
    """Computed macros for a recipe, with explicit grounding coverage.

    `total` and `per_serving` only ever sum grounded contributions. When
    `status` is `PARTIAL`, they undercount the true recipe macros by
    whatever `ungrounded_ingredients` is missing — callers must check
    `status` (and/or `coverage`) before presenting these as authoritative.

    `flags` holds trust-DEMOTING reason codes computed from this object's
    OWN computed values (e.g. an implausible per-serving kcal figure) --
    never from the recipe's self-reported tag macros, and never set by an
    LLM. A non-empty `flags` overrides `status` for trust purposes: see
    `app.services.nutrition_view.trusted_per_serving`/`macro_display_state`,
    the single chokepoint that enforces this, even for an otherwise
    `GROUNDED` recipe. Populated by `app.services.grounding_job.run_grounding`
    at grounding time, not by this schema itself.
    """

    status: GroundingStatus
    servings: int = Field(ge=1)
    total: FoodMacros
    per_serving: FoodMacros
    contributions: list[IngredientContribution] = Field(default_factory=list)
    ungrounded_ingredients: list[str] = Field(default_factory=list)
    coverage: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
