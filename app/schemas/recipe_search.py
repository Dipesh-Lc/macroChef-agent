from pydantic import BaseModel, Field, field_validator

from app.schemas.recipe import Recipe
from app.schemas.user import validate_diet_type_value


class RecipeSearchRequest(BaseModel):
    """The `POST /recipes/search` request body.

    Deliberately standalone fields (mirroring `RecipeDiscoveryRequest` in
    app.schemas.library), not a synthesized `UserProfile` -- a search/browse
    context has no cook-time or disliked-ingredient semantics, so this
    schema does not invent dummy values for fields `UserProfile` requires
    but that don't apply here. This endpoint filters the existing static
    corpus (loaded via app.rag.loaders.load_corpus); it is NOT the
    generative `/library/discover` endpoint.
    """

    cuisines: list[str] | None = None
    allergies: list[str] | None = None
    diet_type: str | None = None
    calorie_min: float | None = Field(default=None, ge=0)
    calorie_max: float | None = Field(default=None, ge=0)
    protein_min: float | None = Field(default=None, ge=0)
    protein_max: float | None = Field(default=None, ge=0)
    carbs_min: float | None = Field(default=None, ge=0)
    carbs_max: float | None = Field(default=None, ge=0)
    fat_min: float | None = Field(default=None, ge=0)
    fat_max: float | None = Field(default=None, ge=0)
    # Mirrors RecipeDiscoveryRequest.count's bound convention (default=10,
    # ge=1, le=50) -- capped at 50 here too, since this is still a
    # per-request linear scan over the full corpus (see routes_recommendations.
    # search_recipes's docstring for why no index/cache is used at this
    # corpus size).
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("diet_type")
    @classmethod
    def _validate_diet_type(cls, value: str | None) -> str | None:
        # Reuses the SAME function UserProfile's own field_validator calls
        # (app.schemas.user.validate_diet_type_value) -- this is the fix for
        # the diet_type validation gap at its source, not a third ad-hoc
        # patch alongside recipe_discovery_service.py's and
        # recipe_validation_service.py's existing ones.
        return validate_diet_type_value(value)


class RecipeSearchResponse(BaseModel):
    results: list[Recipe] = Field(default_factory=list)
    # Count of recipes passing every filter BEFORE `limit` truncation.
    total_matched: int = 0
    # Recipes excluded solely because a calorie/macro range filter was
    # supplied and app.services.nutrition_view.trusted_per_serving returned
    # None (ungrounded/partial nutrition) for them -- see
    # routes_recommendations.search_recipes's docstring for the exact rule
    # (only excluded/counted when at least one calorie/macro filter is
    # active).
    macro_unavailable_excluded: int = 0
