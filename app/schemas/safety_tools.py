"""Request/response contracts for the /tools/* safety-tools API
(app/api/routes_safety_tools.py, roadmap Phase 5 "expose the constraint
engine as an API/MCP server").

These endpoints are thin, unmodified pass-throughs to
app.services.constraint_engine's already-approved functions
(validate_recipe, contains_allergen, violates_diet_type,
derive_allergen_labels) -- see that router module's docstring for the
full safety framing. This module only defines the wire shapes; it makes
no allergy/diet decision of its own and reuses the existing Recipe/
UserProfile schemas rather than inventing parallel ones.
"""

from pydantic import BaseModel, Field

from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile


class ValidateRecipeToolRequest(BaseModel):
    recipe: Recipe
    user_profile: UserProfile


class CheckAllergenToolRequest(BaseModel):
    recipe: Recipe
    allergies: list[str] = Field(default_factory=list)


class CheckAllergenToolResponse(BaseModel):
    contains_allergen: bool


class CheckDietViolationToolRequest(BaseModel):
    recipe: Recipe
    diet_type: str


class CheckDietViolationToolResponse(BaseModel):
    violates_diet_type: bool


class DeriveAllergenLabelsToolRequest(BaseModel):
    ingredient_names: list[str] = Field(default_factory=list)


class DeriveAllergenLabelsToolResponse(BaseModel):
    allergens: list[str]
