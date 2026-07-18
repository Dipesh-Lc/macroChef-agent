from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.recipe import Recipe
from app.schemas.recipe_candidate import RecipeCandidate

SourceMode = Literal["mock", "llm", "external", "hybrid"]


class RecipeDiscoveryRequest(BaseModel):
    """The `/library/discover` request body.

    Deliberately has no `user_id` field: the caller's identity comes only
    from the verified session token (see app.dependencies.get_session_user),
    never from client-supplied request data. Route handlers thread the
    verified user id into the graph separately.
    """

    cuisines: list[str] = Field(default_factory=list)
    meal_type: str | None = None
    diet_type: str | None = None
    max_cook_time_min: int | None = Field(default=None, ge=0)
    difficulty: str | None = None
    count: int = Field(default=10, ge=1, le=50)
    home_cookable: bool = True
    excluded_ingredients: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    extra_preferences: str | None = None
    source_mode: SourceMode = "mock"


class RecipeDiscoveryResponse(BaseModel):
    candidates: list[RecipeCandidate] = Field(default_factory=list)
    debug_trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SaveRecipeCandidatesRequest(BaseModel):
    """The `/library/save` request body. No `user_id` field -- see
    `RecipeDiscoveryRequest`'s docstring."""

    selected_candidates: list[RecipeCandidate] = Field(default_factory=list)


class SaveRecipeCandidatesResponse(BaseModel):
    saved_recipe_ids: list[str] = Field(default_factory=list)
    skipped_duplicates: list[str] = Field(default_factory=list)
    failed_candidates: list[dict] = Field(default_factory=list)
    debug_trace: list[str] = Field(default_factory=list)


class UserRecipeLibraryResponse(BaseModel):
    recipes: list[Recipe] = Field(default_factory=list)


class DeleteRecipeResponse(BaseModel):
    recipe_id: str
    deleted: bool


class ReindexLibraryResponse(BaseModel):
    indexed_count: int
    status: str
