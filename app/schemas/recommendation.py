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
    # No user_id field here, deliberately -- identity for this request is
    # derived exclusively from the verified session token (see
    # app.dependencies.get_session_user), never from client-supplied wire
    # data. This mirrors app.schemas.library's request schemas, which the
    # same fix already applied to the /library routes.
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
    # No user_id field here, deliberately -- identity for this request is
    # derived exclusively from the verified session token (see
    # app.dependencies.get_session_user), never from client-supplied wire
    # data. This mirrors RecommendationRequest above, which the same fix
    # already applied to the /recipes/recommend route; POST /feedback was the
    # third instance of the same bug class (after /library and
    # /recipes/recommend).
    recipe_id: str
    feedback_type: Literal["liked", "disliked", "cooked", "skipped"]
    notes: str | None = None
