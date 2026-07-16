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


# --- 2026-07 diet-leak fix parity ---------------------------------------
#
# recipe_validation_service._violates_requested_diet used to decide
# dairy-free/gluten-free by reading the candidate's stored `allergens`
# labels (populated by derive_allergen_labels' exact-set matching, which
# misses compound ingredient names) instead of routing through
# constraint_engine.contains_allergen's substring matching -- the same gap
# commit 6c89292 already closed for constraint_engine.violates_diet_type.
# Both recipes below are real corpus entries (imp_00d7e68543255f34,
# imp_022adbbb8dbb56c9) that have allergens=[] in the imported data
# precisely because derive_allergen_labels missed their compound dairy /
# gluten ingredient names. See tests/test_constraint_engine.py's matching
# regression block for the constraint_engine-side version of this fix.


def test_dairy_free_catches_compound_cream_cheese_despite_empty_stored_allergens() -> None:
    # Real corpus recipe imp_022adbbb8dbb56c9 ("Crab Dip"): allergens=[] in
    # the imported data, but "cream cheese" is a dairy ingredient that
    # derive_allergen_labels' exact-set matching misses (it isn't literally
    # "dairy" or "cream" or "cheese").
    request = RecipeDiscoveryRequest(user_id="u", diet_type="dairy-free")
    result = RecipeValidationService().validate_candidates(
        [
            _candidate(
                candidate_id="imp_022adbbb8dbb56c9",
                title="Crab Dip",
                ingredients=["1 cream cheese", "2 green onions", "0.5 sherry wine", "1 salt"],
                allergens=[],
                diet_tags=[],
            )
        ],
        request,
    )

    assert result.failed_candidates
    assert not result.valid_candidates
    assert "diet type" in result.failed_candidates[0]["errors"][0].lower()


def test_gluten_free_catches_compound_all_purpose_flour_despite_empty_stored_allergens() -> None:
    # Real corpus recipe imp_00d7e68543255f34 ("Dill Buttermilk Bread"):
    # allergens=[] in the imported data, but "all-purpose flour" and
    # "buttermilk" are gluten/dairy ingredients that derive_allergen_labels'
    # exact-set matching misses.
    request = RecipeDiscoveryRequest(user_id="u", diet_type="gluten-free")
    result = RecipeValidationService().validate_candidates(
        [
            _candidate(
                candidate_id="imp_00d7e68543255f34",
                title="Dill Buttermilk Bread",
                ingredients=[
                    "3 cups all-purpose flour",
                    "1 tsp baking powder",
                    "1.5 cups buttermilk",
                ],
                allergens=[],
                diet_tags=[],
            )
        ],
        request,
    )

    assert result.failed_candidates
    assert not result.valid_candidates


def test_dairy_free_still_rejects_when_stored_allergen_label_is_correct() -> None:
    # Regression: the previous stored-label path must keep working where the
    # label IS correct (e.g. a literal "milk" ingredient, which
    # derive_allergen_labels does catch) -- this fix must not trade one gap
    # for another.
    request = RecipeDiscoveryRequest(user_id="u", diet_type="dairy-free")
    result = RecipeValidationService().validate_candidates(
        [
            _candidate(
                ingredients=["200 g milk", "150 g rice", "80 g broccoli"],
                allergens=["dairy"],
                diet_tags=[],
            )
        ],
        request,
    )

    assert result.failed_candidates
    assert not result.valid_candidates


def test_gluten_free_passes_recipe_with_no_gluten_ingredients() -> None:
    # Regression: a genuinely gluten-free recipe must not be caught by the
    # new contains_allergen path.
    request = RecipeDiscoveryRequest(user_id="u", diet_type="gluten-free")
    result = RecipeValidationService().validate_candidates(
        [_candidate(diet_tags=["high-protein", "dairy-free"])],
        request,
    )

    assert result.valid_candidates
    assert not result.failed_candidates


def test_vegetarian_diet_tag_path_is_unchanged() -> None:
    # vegetarian/vegan/high-protein check candidate.diet_tags, a separate
    # mechanism out of scope for this fix -- confirm it still works.
    request = RecipeDiscoveryRequest(user_id="u", diet_type="vegetarian")
    result = RecipeValidationService().validate_candidates(
        [_candidate(diet_tags=["high-protein", "dairy-free"])],  # no "vegetarian" tag
        request,
    )

    assert result.failed_candidates
    assert not result.valid_candidates


def test_vegan_diet_tag_path_is_unchanged() -> None:
    request = RecipeDiscoveryRequest(user_id="u", diet_type="vegan")
    result = RecipeValidationService().validate_candidates(
        [_candidate(diet_tags=["vegan", "high-protein"])],
        request,
    )

    assert result.valid_candidates
    assert not result.failed_candidates


def test_high_protein_diet_tag_path_is_unchanged() -> None:
    request = RecipeDiscoveryRequest(user_id="u", diet_type="high-protein")
    result = RecipeValidationService().validate_candidates(
        [_candidate(diet_tags=["dairy-free"])],  # no "high-protein" tag
        request,
    )

    assert result.failed_candidates
    assert not result.valid_candidates
