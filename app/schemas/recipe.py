import logging

from pydantic import BaseModel, Field, field_validator

from app.schemas.ingredient import Ingredient

logger = logging.getLogger(__name__)


class Recipe(BaseModel):
    recipe_id: str
    title: str
    cuisine: str | None = None
    meal_type: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
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

    @field_validator("ingredients", mode="after")
    @classmethod
    def _drop_empty_ingredients(
        cls, ingredients: list[Ingredient], info
    ) -> list[Ingredient]:
        # Tolerant, non-destructive cleanup: a stray "" / "   " ingredient (from a
        # loader, DB blob, or candidate conversion) is dropped rather than
        # persisted as name='' or raised over. This is the single chokepoint for
        # every Recipe assembly path (loaders.load_recipes, RecipeCandidate.
        # to_recipe, direct construction). The drop is logged so a loader
        # emitting empties in bulk (e.g. at corpus-scale in item 1.3) is visible.
        kept = [item for item in ingredients if item.name and item.name.strip()]
        dropped = len(ingredients) - len(kept)
        if dropped:
            identifier = info.data.get("recipe_id") or info.data.get("title") or "<unknown>"
            logger.debug(
                "Dropped %d empty-name ingredient(s) while assembling recipe %s",
                dropped,
                identifier,
            )
        return kept
