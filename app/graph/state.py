from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.inventory import ConfirmedIngredient, InventoryObservation
from app.schemas.recipe import Recipe
from app.schemas.recommendation import MealRecommendation, RecipeScore, RejectedRecipe
from app.schemas.shopping import ShoppingItem
from app.schemas.user import UserProfile


class MacroChefState(BaseModel):
    user_id: str = "demo_user"
    input_type: Literal["text", "image", "manual", "mixed"] = "text"
    image_path: str | None = None
    typed_ingredients: str | None = None
    user_profile: UserProfile | None = None
    raw_inventory_observations: list[InventoryObservation] = Field(default_factory=list)
    confirmed_inventory: list[ConfirmedIngredient] = Field(default_factory=list)
    cuisine_preference: str | None = None
    meal_type: str | None = None
    candidate_recipes: list[Recipe] = Field(default_factory=list)
    rejected_recipes: list[RejectedRecipe] = Field(default_factory=list)
    scored_recipes: list[RecipeScore] = Field(default_factory=list)
    final_recommendations: list[MealRecommendation] = Field(default_factory=list)
    shopping_list: list[ShoppingItem] = Field(default_factory=list)
    memory_update: str | None = None
    constraints: dict[str, object] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    debug_trace: list[str] = Field(default_factory=list)


def ensure_state(state: MacroChefState | dict) -> MacroChefState:
    if isinstance(state, MacroChefState):
        return state
    return MacroChefState.model_validate(state)


def state_update(state: MacroChefState, **updates):
    data = state.model_dump()
    data.update(updates)
    return data
