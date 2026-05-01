from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from app.schemas.recipe import Recipe
from app.utils.ingredient_normalizer import normalize_ingredient

SourceType = Literal["mock", "ai_generated", "external", "curated", "user_added"]


class RecipeCandidate(BaseModel):
    candidate_id: str
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    description: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    cook_time_min: int | None = Field(default=None, ge=0)
    difficulty: str | None = None
    servings: int | None = Field(default=1, ge=1)
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)
    allergens: list[str] = Field(default_factory=list)
    diet_tags: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    image_url: str | None = None
    image_path: str | None = None
    source_type: SourceType
    source_name: str | None = None
    source_url: str | None = None
    home_cookable_score: float = Field(default=1.0, ge=0, le=1)
    validation_warnings: list[str] = Field(default_factory=list)

    def to_recipe(self, user_id: str) -> Recipe:
        stable_id = uuid5(NAMESPACE_URL, f"macrochef:{user_id}:{self.title}:{self.cuisine}")
        recipe_id = f"user_{stable_id.hex[:16]}"
        return Recipe(
            recipe_id=recipe_id,
            title=self.title,
            cuisine=self.cuisine,
            meal_type=self.meal_type,
            ingredients=[item.strip() for item in self.ingredients if item.strip()],
            instructions=[item.strip() for item in self.instructions if item.strip()],
            allergens=[normalize_ingredient(item).lower() for item in self.allergens if item],
            diet_tags=[item.strip().lower() for item in self.diet_tags if item.strip()],
            cook_time_min=self.cook_time_min,
            calories=self.calories,
            protein_g=self.protein_g,
            carbs_g=self.carbs_g,
            fat_g=self.fat_g,
            fiber_g=self.fiber_g,
            description=self.description,
            difficulty=self.difficulty,
            servings=self.servings,
            equipment=[item.strip().lower() for item in self.equipment if item.strip()],
            image_url=self.image_url,
            image_path=self.image_path,
            source_type=self.source_type,
            source_name=self.source_name,
            source_url=self.source_url,
            owner_user_id=user_id,
            is_user_saved=True,
            is_active=True,
        )
