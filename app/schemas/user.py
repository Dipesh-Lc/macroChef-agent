from pydantic import BaseModel, Field, field_validator

# Diet types app.services.constraint_engine.violates_diet_type actually
# enforces deterministically. A diet_type outside this set (e.g. "keto",
# "paleo", "halal") must be rejected at intake rather than silently accepted:
# violates_diet_type would return False for every recipe, which reads as a
# safety guarantee ("your halal request was honored") the app isn't making.
SUPPORTED_DIET_TYPES = {"vegetarian", "vegan", "gluten-free", "dairy-free"}
NO_RESTRICTION_DIET_TYPES = {"none", "omnivore", "no restriction"}


def validate_diet_type_value(value: str | None) -> str | None:
    """Reject any `diet_type` outside SUPPORTED_DIET_TYPES/NO_RESTRICTION_DIET_TYPES.

    Single source of truth for this intake-time check -- `UserProfile`'s own
    `field_validator` below calls this, and any other request schema that
    accepts a freeform `diet_type` string (e.g. `RecipeSearchRequest`, see
    app.schemas.recipe_search) should reuse this SAME function as its
    `field_validator` rather than hand-rolling a second copy. Two services
    (recipe_discovery_service.py, recipe_validation_service.py) already had
    to separately patch around the absence of this check at their own call
    sites -- this function is the fix at the source, not a third patch.

    A `diet_type` outside this set (e.g. "keto", "paleo", "halal") must be
    rejected at intake rather than silently accepted: `violates_diet_type`
    (app.services.constraint_engine) would raise a `ValueError` for it, and
    letting that reach a caller unguarded is exactly the gap this function
    closes -- reject with a normal Pydantic `ValidationError` (422) instead
    of a 500 from an unhandled exception deep in the constraint engine.
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in NO_RESTRICTION_DIET_TYPES or normalized in SUPPORTED_DIET_TYPES:
        return value
    raise ValueError(
        f"Unsupported diet_type {value!r}. MacroChef only enforces "
        f"{sorted(SUPPORTED_DIET_TYPES)} today; unrecognized diet types "
        "are rejected instead of silently passing every recipe as safe."
    )


class MacroTargets(BaseModel):
    calories: int | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)


class UserProfile(BaseModel):
    user_id: str = "demo_user"
    allergies: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    diet_type: str | None = None
    preferred_cuisines: list[str] = Field(default_factory=list)
    macro_targets: MacroTargets = Field(default_factory=MacroTargets)
    max_cook_time_min: int | None = Field(default=None, ge=1)

    @field_validator("diet_type")
    @classmethod
    def _validate_diet_type(cls, value: str | None) -> str | None:
        return validate_diet_type_value(value)
