from pydantic import BaseModel, Field


class Recipe(BaseModel):
    recipe_id: str
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    diet_tags: list[str] = Field(default_factory=list)
    cook_time_min: int | None = Field(default=None, ge=0)
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)
    description: str | None = None
    difficulty: str | None = None
    servings: int | None = Field(default=1, ge=1)
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    image_path: str | None = None
    source_type: str | None = "base"
    source_name: str | None = None
    source_url: str | None = None
    owner_user_id: str | None = None
    is_user_saved: bool = False
    is_active: bool = True
