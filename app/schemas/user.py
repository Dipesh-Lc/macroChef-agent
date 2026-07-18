from pydantic import BaseModel, Field, field_validator

# Diet types app.services.constraint_engine.violates_diet_type actually
# enforces deterministically. A diet_type outside this set (e.g. "keto",
# "paleo", "halal") must be rejected at intake rather than silently accepted:
# violates_diet_type would return False for every recipe, which reads as a
# safety guarantee ("your halal request was honored") the app isn't making.
SUPPORTED_DIET_TYPES = {"vegetarian", "vegan", "gluten-free", "dairy-free"}
NO_RESTRICTION_DIET_TYPES = {"none", "omnivore", "no restriction"}


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
