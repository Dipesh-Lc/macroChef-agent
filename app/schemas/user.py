from pydantic import BaseModel, Field


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
