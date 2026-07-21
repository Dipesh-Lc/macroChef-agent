"""Phase 5 (pulled-forward Wave-3 fill): expose the constraint engine as a
small, standalone "safety tools" HTTP API that an external AI agent or
developer can call directly -- without going through MacroChef's full
recommend/day-plan pipeline -- to get deterministic allergy/diet-type
filtering.

SAFETY (mandatory, verifiable): every endpoint below is a THIN, UNMODIFIED
pass-through to an already safety-approved function in
app.services.constraint_engine (validate_recipe, contains_allergen,
violates_diet_type, derive_allergen_labels). No endpoint adds caching,
normalization, or any other transformation that could make its answer
differ from calling the underlying function directly -- see
tests/test_routes_safety_tools.py's "endpoint output == direct function
call output" test class, which is the load-bearing correctness property
for this whole module. This module makes no allergy/diet DECISION of its
own; it only adds ACCESS to a decision constraint_engine already makes.

Disclaimer (Honest Scope, CLAUDE.md): this is a hobby project, not medical
advice. As of the current README/adjudicated benchmark run
(`20260719T115815Z`), the adversarial safety benchmark's 259
release-blocking (`inherent`-severity) cases are judge-flagged **16/259**,
adjudicated-true **0/259** (see
data/evaluation/adjudication_20260719T115815Z.md; the raw judge-flagged
count is always published alongside the adjudicated one, per CLAUDE.md's
"Honest scope" rule) -- callers with a food allergy must still verify
ingredients themselves.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_safety_tools_rate_limit
from app.schemas.recommendation import ValidationResult
from app.schemas.safety_tools import (
    CheckAllergenToolRequest,
    CheckAllergenToolResponse,
    CheckDietViolationToolRequest,
    CheckDietViolationToolResponse,
    DeriveAllergenLabelsToolRequest,
    DeriveAllergenLabelsToolResponse,
    ValidateRecipeToolRequest,
)
from app.services.constraint_engine import (
    contains_allergen,
    derive_allergen_labels,
    validate_recipe,
    violates_diet_type,
)

router = APIRouter(
    prefix="/tools",
    tags=["safety-tools"],
    dependencies=[Depends(require_safety_tools_rate_limit)],
)


@router.post("/validate-recipe", response_model=ValidationResult)
def validate_recipe_tool(request: ValidateRecipeToolRequest) -> ValidationResult:
    """Direct pass-through to constraint_engine.validate_recipe -- runs every
    hard constraint (allergens, disliked ingredients, diet type, cook time)
    in the same order and returns the exact same ValidationResult a caller
    would get by importing and calling that function themselves."""
    return validate_recipe(request.recipe, request.user_profile)


@router.post("/check-allergen", response_model=CheckAllergenToolResponse)
def check_allergen_tool(request: CheckAllergenToolRequest) -> CheckAllergenToolResponse:
    """Direct pass-through to constraint_engine.contains_allergen."""
    return CheckAllergenToolResponse(
        contains_allergen=contains_allergen(request.recipe, request.allergies)
    )


@router.post("/check-diet-violation", response_model=CheckDietViolationToolResponse)
def check_diet_violation_tool(
    request: CheckDietViolationToolRequest,
) -> CheckDietViolationToolResponse:
    """Direct pass-through to constraint_engine.violates_diet_type.

    violates_diet_type raises ValueError for a diet_type it was never taught
    to enforce (see that function's docstring: it fails loudly rather than
    silently claiming a recipe is safe) -- surfaced here as 422, mirroring
    the existing ValueError->422 pattern in routes_day_planner.py, not
    swallowed or reinterpreted.
    """
    try:
        violates = violates_diet_type(request.recipe, request.diet_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CheckDietViolationToolResponse(violates_diet_type=violates)


@router.post("/derive-allergen-labels", response_model=DeriveAllergenLabelsToolResponse)
def derive_allergen_labels_tool(
    request: DeriveAllergenLabelsToolRequest,
) -> DeriveAllergenLabelsToolResponse:
    """Direct pass-through to constraint_engine.derive_allergen_labels."""
    return DeriveAllergenLabelsToolResponse(
        allergens=derive_allergen_labels(request.ingredient_names)
    )
