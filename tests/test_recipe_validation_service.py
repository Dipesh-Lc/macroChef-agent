from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.recipe_validation_service import RecipeValidationService


def _candidate(**updates) -> RecipeCandidate:
    data = {
        "candidate_id": "c_valid",
        "title": "Chicken Rice Bowl",
        "cuisine": "Japanese",
        "meal_type": "dinner",
        "description": "A practical bowl.",
        "ingredients": ["150 g chicken breast", "150 g rice", "80 g broccoli"],
        "instructions": ["Cook rice.", "Sear chicken."],
        "cook_time_min": 25,
        "calories": 560,
        "protein_g": 45,
        "carbs_g": 60,
        "fat_g": 12,
        "fiber_g": 6,
        "allergens": [],
        "diet_tags": ["high-protein", "dairy-free"],
        "equipment": ["skillet"],
        "source_type": "mock",
    }
    data.update(updates)
    return RecipeCandidate.model_validate(data)


def test_missing_title_fails() -> None:
    result = RecipeValidationService().validate_candidates([_candidate(title="")])

    assert result.failed_candidates
    assert not result.valid_candidates


def test_too_few_ingredients_fails() -> None:
    result = RecipeValidationService().validate_candidates(
        [_candidate(ingredients=["150 g chicken breast", "150 g rice"])]
    )

    assert result.failed_candidates


def test_allergy_conflict_fails() -> None:
    request = RecipeDiscoveryRequest(user_id="u", allergies=["soy"])
    result = RecipeValidationService().validate_candidates(
        [_candidate(allergens=["soy"])],
        request,
    )

    assert result.failed_candidates


def test_missing_image_gets_placeholder() -> None:
    result = RecipeValidationService().validate_candidates([_candidate(image_url=None)])

    assert result.valid_candidates[0].image_url


def test_missing_macros_warn_but_do_not_fail() -> None:
    result = RecipeValidationService().validate_candidates(
        [_candidate(calories=None, protein_g=None)]
    )

    assert result.valid_candidates
    assert result.valid_candidates[0].validation_warnings
