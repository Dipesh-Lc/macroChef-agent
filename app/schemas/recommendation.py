from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.inventory import ConfirmedIngredient, InventoryObservation
from app.schemas.recipe import Recipe
from app.schemas.shopping import ShoppingItem
from app.schemas.user import UserProfile


class RecipeScore(BaseModel):
    recipe_id: str
    pantry_match_score: float = Field(ge=0, le=1)
    macro_fit_score: float = Field(ge=0, le=1)
    time_score: float = Field(ge=0, le=1)
    preference_score: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    missing_ingredients: list[str] = Field(default_factory=list)
    used_ingredients: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class MealRecommendation(BaseModel):
    recipe: Recipe
    score: RecipeScore
    explanation: str
    shopping_list: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    is_valid: bool
    rejection_reason: str | None = None


class RejectedRecipe(BaseModel):
    recipe_id: str
    title: str
    reason: str


class RecommendationRequest(BaseModel):
    user_id: str = "demo_user"
    input_type: Literal["text", "image", "manual", "mixed"] = "text"
    image_path: str | None = None
    typed_ingredients: str | None = None
    confirmed_inventory: list[ConfirmedIngredient] | None = None
    user_profile: UserProfile
    cuisine_preference: str | None = None
    meal_type: str | None = None


class RecommendationResponse(BaseModel):
    recommendations: list[MealRecommendation] = Field(default_factory=list)
    shopping_list: list[ShoppingItem] = Field(default_factory=list)
    rejected_recipes: list[RejectedRecipe] = Field(default_factory=list)
    inventory_observations: list[InventoryObservation] = Field(default_factory=list)
    debug_trace: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    user_id: str
    recipe_id: str
    feedback_type: Literal["liked", "disliked", "cooked", "skipped"]
    notes: str | None = None
