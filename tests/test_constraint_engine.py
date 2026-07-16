import pytest
from pydantic import ValidationError

from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.constraint_engine import validate_recipe


def _profile(**kwargs) -> UserProfile:
    return UserProfile(user_id="u", macro_targets=MacroTargets(), **kwargs)


def _recipe(**kwargs) -> Recipe:
    defaults = {
        "recipe_id": "r",
        "title": "Test Recipe",
        "ingredients": ["rice", "spinach"],
        "instructions": ["Cook."],
        "allergens": [],
        "diet_tags": ["gluten-free"],
        "cook_time_min": 20,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


def test_rejects_peanut_recipe_for_peanut_allergy() -> None:
    recipe = _recipe(ingredients=["tofu", "peanut butter"], allergens=["peanut"])
    result = validate_recipe(recipe, _profile(allergies=["peanut"]))

    assert not result.is_valid
    assert "allergen" in result.rejection_reason.lower()


def test_rejects_dairy_recipe_for_dairy_allergy() -> None:
    recipe = _recipe(ingredients=["Greek yogurt", "berries"], allergens=["dairy"])
    result = validate_recipe(recipe, _profile(allergies=["dairy"]))

    assert not result.is_valid


def test_rejects_milk_alias_for_parmesan() -> None:
    recipe = _recipe(ingredients=["zucchini noodles", "parmesan"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["milk"]))

    assert not result.is_valid


def test_rejects_tree_nut_alias_for_almond_flour() -> None:
    recipe = _recipe(ingredients=["ground turkey", "almond flour"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert not result.is_valid


def test_rejects_seafood_alias_for_salmon() -> None:
    recipe = _recipe(ingredients=["salmon", "rice", "cucumber"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["seafood"]))

    assert not result.is_valid


def test_rejects_disliked_ingredient() -> None:
    recipe = _recipe(ingredients=["rice", "mushroom"])
    result = validate_recipe(recipe, _profile(disliked_ingredients=["mushroom"]))

    assert not result.is_valid
    assert "disliked" in result.rejection_reason.lower()


def test_rejects_over_max_cook_time() -> None:
    recipe = _recipe(cook_time_min=45)
    result = validate_recipe(recipe, _profile(max_cook_time_min=30))

    assert not result.is_valid
    assert "time" in result.rejection_reason.lower()


def test_allows_safe_recipe() -> None:
    recipe = _recipe()
    result = validate_recipe(recipe, _profile(allergies=["peanut"], max_cook_time_min=30))

    assert result.is_valid


def test_allergen_detected_regardless_of_quantity() -> None:
    # Safety must never depend on amount — an allergen in any quantity is a violation.
    recipe = _recipe(ingredients=["0.1 g peanut butter", "tofu"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["peanut"]))

    assert not result.is_valid


def test_structured_ingredient_allergen_rejected() -> None:
    # Allergen matching reads the structured ingredient's name.
    recipe = _recipe(ingredients=[Ingredient(name="peanut butter", amount=15, unit="g")])
    result = validate_recipe(recipe, _profile(allergies=["peanut"]))

    assert not result.is_valid


def test_milk_allergen_caught_before_and_after_quantity_parser_range_fix() -> None:
    # app/utils/quantity_parser.py item: "2-4 tbsp milk" used to parse to
    # name="-4 tbsp milk" (amount/unit dropped, en dash left glued to "4").
    # It now parses to name="milk", amount=3.0, unit="tbsp". Both the
    # before-shape and the after-shape must trip a milk allergy so the fix is
    # provably non-regressive on the safety path (constraint_engine reads
    # only ingredient names, never amount/unit).
    before = _recipe(ingredients=[Ingredient(name="–4 tbsp milk", amount=2.0, unit=None)], allergens=[])
    after = _recipe(ingredients=[Ingredient(name="milk", amount=3.0, unit="tbsp")], allergens=[])

    assert not validate_recipe(before, _profile(allergies=["milk"])).is_valid
    assert not validate_recipe(after, _profile(allergies=["milk"])).is_valid


def test_peanut_allergen_caught_before_and_after_glued_unicode_fraction_fix() -> None:
    # Same item: "1½ cup peanut butter" used to parse to
    # name="½ cup peanut butter" (amount/unit dropped). It now parses to
    # name="peanut butter", amount=1.5, unit="cup". Both shapes must trip a
    # peanut allergy.
    before = _recipe(ingredients=[Ingredient(name="½ cup peanut butter", amount=1.0, unit=None)], allergens=[])
    after = _recipe(ingredients=[Ingredient(name="peanut butter", amount=1.5, unit="cup")], allergens=[])

    assert not validate_recipe(before, _profile(allergies=["peanut"])).is_valid
    assert not validate_recipe(after, _profile(allergies=["peanut"])).is_valid


def test_whole_egg_still_triggers_egg_allergen() -> None:
    # "eggs"/"egg" were renamed to "whole egg" (nutrition grounding item 1.4)
    # to disambiguate against USDA's "egg white" record. ALLERGEN_ALIASES["egg"]
    # is the literal set {"egg", "egg whites", "eggs", "mayonnaise"} and does
    # NOT contain "whole egg" -- this must still be caught via ingredient_matches'
    # substring fallback ("egg" in "whole egg"), not exact set membership.
    recipe = _recipe(ingredients=[Ingredient(name="whole egg", amount=1, unit=None)], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["egg"]))

    assert not result.is_valid


def test_whole_egg_still_blocks_vegan_diet() -> None:
    # Same rename, same non-membership risk, but reached via
    # violates_diet_type's DIET_TYPE_EXCLUDED_TERMS["vegan"] path instead of
    # contains_allergen directly.
    recipe = _recipe(ingredients=[Ingredient(name="whole egg", amount=1, unit=None)], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegan"))

    assert not result.is_valid
    assert "vegan" in result.rejection_reason.lower()


# --- 2026-07 corpus diet-leak audit regressions -----------------------------
#
# Root cause 2 (matching bug): gluten-free/dairy-free used to check
# recipe.allergens (populated by derive_allergen_labels' exact-set matching,
# which misses compound ingredient names) instead of contains_allergen's
# substring matching. Both recipes below are real corpus entries
# (imp_00d7e68543255f34, imp_022adbbb8dbb56c9) with allergens=[] in the
# imported data precisely because derive_allergen_labels missed them.


def test_gluten_free_catches_compound_flour_and_buttermilk() -> None:
    recipe = _recipe(
        title="Dill Buttermilk Bread",
        ingredients=["all-purpose flour", "baking soda", "buttermilk"],
        allergens=[],
        diet_tags=[],
    )
    result = validate_recipe(recipe, _profile(diet_type="gluten-free"))

    assert not result.is_valid


def test_dairy_free_catches_buttermilk_and_cream_cheese() -> None:
    bread = _recipe(
        title="Dill Buttermilk Bread",
        ingredients=["all-purpose flour", "baking soda", "buttermilk"],
        allergens=[],
        diet_tags=[],
    )
    crab_dip = _recipe(
        title="Crab Dip",
        ingredients=["cream cheese", "green onions", "sherry wine", "salt"],
        allergens=[],
        diet_tags=[],
    )

    assert not validate_recipe(bread, _profile(diet_type="dairy-free")).is_valid
    assert not validate_recipe(crab_dip, _profile(diet_type="dairy-free")).is_valid


# Root cause 1 (stale list): vegan/vegetarian's blocker vocabulary lagged the
# corpus. These terms come from the same audit; butter/parmesan/sour cream/
# mayonnaise/heavy cream aren't listed explicitly because they're now caught
# via the shared ALLERGEN_ALIASES dairy/egg sets (see MEAT_ALIASES comment).
@pytest.mark.parametrize(
    "diet_type,ingredient",
    [
        ("vegetarian", "bacon"),
        ("vegetarian", "ham"),
        ("vegetarian", "chicken broth"),
        ("vegetarian", "worcestershire sauce"),
        ("vegetarian", "gelatin"),
        ("vegetarian", "pancetta"),
        ("vegetarian", "rump steak"),
        ("vegetarian", "halibut steaks"),
        ("vegan", "bacon"),
        ("vegan", "butter"),
        ("vegan", "parmesan"),
        ("vegan", "sour cream"),
        ("vegan", "mayonnaise"),
        ("vegan", "heavy cream"),
        ("vegan", "half-and-half"),
        ("vegan", "ricotta"),
    ],
)
def test_diet_blockers_cover_audit_surfaced_corpus_vocabulary(diet_type: str, ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert not result.is_valid


# Root cause 2b (found while re-running the audit after the first fix):
# ingredient_matches() re-normalizes its `candidate` argument internally,
# re-applying SYNONYMS["chicken"] = "chicken breast" on top of the
# normalization _normalized_terms already did. That collapsed the broad
# blocker term "chicken" into a specific cut, so it silently stopped
# matching every OTHER cut -- 51/629 vegan-safe and 108/2616 vegetarian-safe
# corpus recipes leaked chicken (drumsticks, thighs, livers, wings, broth,
# bouillon) before _recipe_contains_any_term stopped routing through
# ingredient_matches for this check.
@pytest.mark.parametrize(
    "ingredient",
    [
        "chicken drumsticks",
        "chicken thighs",
        "chicken livers",
        "chicken bouillon cubes",
        "frying chickens",
        "boneless skinless chicken thighs",
    ],
)
def test_chicken_cut_names_still_block_vegetarian_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["halibut steaks", "sole fillets", "red snapper fillets", "flounder fillets"])
def test_additional_fish_species_block_vegan_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegan"))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["graham cracker crumbs", "phyllo pastry", "spaghetti", "crouton"])
def test_additional_gluten_vocabulary_blocks_gluten_free_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="gluten-free"))

    assert not result.is_valid


def test_unsupported_diet_type_rejected_at_profile_intake() -> None:
    # A freeform diet_type MacroChef doesn't enforce (halal/keto/paleo) must
    # fail loudly at intake rather than silently pass every recipe as safe.
    with pytest.raises(ValidationError):
        _profile(diet_type="halal")


# --- 2026-07 confirmed allergen-alias gaps (fish/worcestershire, peanut/satay,
# tree nut/pine nuts, tree nut/marzipan) -------------------------------------
#
# Human-confirmed gaps: worcestershire sauce (anchovy-based), satay sauce
# (peanut-based), pine nuts, and marzipan (almond paste) were all wrongly
# served to matching allergies. See ALLERGEN_ALIASES["fish"/"peanut"/
# "tree nut"] inline comments in constraint_engine.py for the authoritative
# source cited per addition. Sanity cases (anchovy paste/fish, peanut
# butter/peanut) are re-asserted alongside the new gap cases to prove the
# fix didn't regress the already-working path.
#
# 2026-07 follow-up (advisor review): "seafood" and "nuts" are separate keys
# from "fish"/"tree nut"/"peanut" in ALLERGEN_ALIASES and had their own,
# independent gaps -- "seafood" + worcestershire sauce and "nuts" +
# groundnut oil were both served. The accented "saté" transliteration is
# pinned directly (not just "satay sauce") since it's the one most likely to
# be typed by a user and is a distinct dict key. "amaretto" is pinned against
# "tree nut" per the policy-consistency addition (ambiguous nut content
# resolves toward blocking).


@pytest.mark.parametrize(
    "allergy,ingredient",
    [
        ("fish", "anchovy paste"),
        ("peanut", "peanut butter"),
        ("fish", "worcestershire sauce"),
        ("peanut", "satay sauce"),
        ("tree nut", "pine nuts"),
        ("tree nut", "marzipan"),
        ("peanut", "saté"),
        ("seafood", "worcestershire sauce"),
        ("nuts", "groundnut oil"),
        ("tree nut", "amaretto"),
    ],
)
def test_confirmed_allergen_alias_gaps_now_blocked(allergy: str, ingredient: str) -> None:
    recipe = _recipe(ingredients=[Ingredient(name=ingredient, amount=1, unit="tbsp")], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=[allergy]))

    assert not result.is_valid


def test_worcestershire_still_blocks_vegetarian_diet_after_fish_addition() -> None:
    # "worcestershire" was already in MEAT_ALIASES (vegetarian/vegan path)
    # before this fix; adding it to ALLERGEN_ALIASES["fish"] (allergy path)
    # must be additive and not disturb that existing behavior.
    recipe = _recipe(ingredients=["rice", "worcestershire sauce"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


def test_water_chestnut_not_over_blocked_by_tree_nut_additions() -> None:
    # Regression guard for the tree-nut additions in this change: a near-miss
    # name that merely shares the word "nut" must still be served, not
    # blocked.
    #
    # NOTE: "eggplant" (egg allergy) and "buckwheat" (wheat allergy) were
    # investigated as the same kind of near-miss guard, per the task spec,
    # and found to ALREADY over-block on main before this change (substring
    # matches on "egg" and "wheat" respectively) -- pre-existing, unrelated
    # to the fish/peanut/tree-nut additions here, so they are reported to
    # the orchestrator rather than fixed as part of this scoped change.
    recipe = _recipe(ingredients=["rice", "water chestnut"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert result.is_valid
