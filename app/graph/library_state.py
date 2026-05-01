from typing import Any

from pydantic import BaseModel, Field

from app.schemas.recipe import Recipe
from app.schemas.recipe_candidate import RecipeCandidate


class RecipeLibraryBuilderState(BaseModel):
    user_id: str
    cuisines: list[str] = Field(default_factory=list)
    meal_type: str | None = None
    diet_type: str | None = None
    max_cook_time_min: int | None = None
    difficulty: str | None = None
    count: int = 10
    home_cookable: bool = True
    allergies: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    extra_preferences: str | None = None
    source_mode: str = "mock"
    selected_candidates: list[RecipeCandidate] = Field(default_factory=list)

    raw_candidates: list[dict[str, Any]] = Field(default_factory=list)
    normalized_candidates: list[RecipeCandidate] = Field(default_factory=list)
    validated_candidates: list[RecipeCandidate] = Field(default_factory=list)
    duplicate_candidates: list[RecipeCandidate] = Field(default_factory=list)
    failed_candidates: list[dict] = Field(default_factory=list)
    saved_recipes: list[Recipe] = Field(default_factory=list)
    saved_recipe_ids: list[str] = Field(default_factory=list)

    debug_trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    skipped_duplicates: list[str] = Field(default_factory=list)
    indexed_count: int = 0


def ensure_library_state(state: RecipeLibraryBuilderState | dict) -> RecipeLibraryBuilderState:
    if isinstance(state, RecipeLibraryBuilderState):
        return state
    return RecipeLibraryBuilderState.model_validate(state)


def library_state_update(state: RecipeLibraryBuilderState, **updates):
    return state.model_copy(update=updates).model_dump()
