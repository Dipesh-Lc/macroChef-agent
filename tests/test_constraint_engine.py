import pytest
from pydantic import ValidationError

from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.rag.loaders import load_recipes
from app.services.constraint_engine import (
    ALLERGEN_ALIASES,
    contains_allergen,
    derive_allergen_labels,
    validate_recipe,
    violates_diet_type,
)


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
        # 2026-07 follow-up: chestnut/crawfish/sea bass gaps (see the
        # chestnut/water-chestnut lookalike tests below for the trickier
        # near-miss half of this fix).
        ("tree nut", "fresh chestnuts"),
        ("tree nut", "chestnut puree"),
        ("shellfish", "crawfish tails"),
        ("shellfish", "crawfish fat"),
        ("fish", "sea bass fillet"),
        ("fish", "filets of fresh sea bass"),
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


# --- Chestnut/water-chestnut lookalike exclusion ----------------------------
#
# "chestnut" was added to _TREE_NUT (a real, regulated tree nut per FARE),
# but the bare noun also substring-matches "water chestnut" (Eleocharis
# dulcis), an unrelated aquatic sedge that is NOT a tree nut. A naive add
# would fix the real-chestnut gap and simultaneously regress every
# water-chestnut ingredient into a false positive (the test immediately
# above, plus safe_009/morphology_006 in the safety benchmark). The
# _LOOKALIKE_EXCLUSIONS mechanism in constraint_engine.py exists to prevent
# exactly that regression -- these tests cover every corpus-observed
# water-chestnut spelling plus the one real attack the mechanism must NOT
# allow: hiding a real chestnut behind an unrelated water-chestnut
# ingredient in the same recipe.


@pytest.mark.parametrize(
    "ingredient",
    [
        "water chestnut",
        "water chestnuts",
        "sliced water chestnuts",
        "water chestnut flour",
    ],
)
def test_water_chestnut_variants_not_blocked_by_tree_nut_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert result.is_valid


@pytest.mark.parametrize("ingredient", ["fresh chestnuts", "chestnut puree"])
def test_real_chestnut_still_blocked_by_tree_nut_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert not result.is_valid


def test_real_chestnut_cannot_hide_behind_water_chestnut_in_same_recipe() -> None:
    # The exclusion is per-ingredient-term, not per-recipe: a recipe with
    # BOTH a lookalike ("water chestnuts") AND a real tree nut ("fresh
    # chestnuts") must still be caught, on the strength of the real
    # ingredient's own term. A per-recipe exclusion would be a genuine
    # safety hole -- an attacker (or an unlucky recipe) could hide a real
    # chestnut behind an unrelated water-chestnut ingredient.
    recipe = _recipe(ingredients=["water chestnuts", "fresh chestnuts", "rice"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert not result.is_valid


# --- ALLERGEN_ALIASES composition restructure -------------------------------
#
# ALLERGEN_ALIASES used to keep hand-synced duplicate sets (dairy==milk,
# peanut==peanuts, soy==soya, egg==eggs) and hand-copied composed sets
# (seafood as a copy of fish+shellfish+crustacean, nuts as a copy of tree
# nut+peanut). That's exactly the shape of hazard commit 1cba9a9 fixed once
# for "fish"/Worcestershire sauce and missed for the identical "seafood" gap,
# because nothing structurally tied the two hand-maintained sets together.
#
# The table now composes every public key from private frozenset base sets
# (_FISH, _CRUSTACEAN, _MOLLUSK, _TREE_NUT, _PEANUT, _DAIRY, _SOY, _EGG,
# _WHEAT), so a duplicate pair is the *same object* and a composed key is a
# structural (not copied) union. These tests assert the composition
# invariants directly -- this is the real regression guard: it fails loudly
# if a future edit reintroduces a hand-copied, driftable set.


def test_allergen_alias_exact_duplicates_are_identical_objects() -> None:
    # Not just equal -- the *same* frozenset object, so an edit to one can
    # never leave the other stale.
    assert ALLERGEN_ALIASES["dairy"] is ALLERGEN_ALIASES["milk"]
    assert ALLERGEN_ALIASES["peanut"] is ALLERGEN_ALIASES["peanuts"]
    assert ALLERGEN_ALIASES["soy"] is ALLERGEN_ALIASES["soya"]
    assert ALLERGEN_ALIASES["egg"] is ALLERGEN_ALIASES["eggs"]


def test_allergen_alias_composed_keys_are_structural_supersets() -> None:
    assert ALLERGEN_ALIASES["seafood"] >= ALLERGEN_ALIASES["fish"]
    assert ALLERGEN_ALIASES["seafood"] >= ALLERGEN_ALIASES["shellfish"]
    assert ALLERGEN_ALIASES["seafood"] >= ALLERGEN_ALIASES["crustacean"]
    assert ALLERGEN_ALIASES["shellfish"] >= ALLERGEN_ALIASES["crustacean"]
    assert ALLERGEN_ALIASES["nuts"] >= ALLERGEN_ALIASES["tree nut"]
    assert ALLERGEN_ALIASES["nuts"] >= ALLERGEN_ALIASES["peanut"]
    assert ALLERGEN_ALIASES["gluten"] >= ALLERGEN_ALIASES["wheat"]


def test_seafood_blocks_white_fish_via_explicit_table_entry() -> None:
    # Must be an explicit member of the resolved set, not an accident of
    # substring matching ("white fish" happening to contain "fish").
    assert "white fish" in ALLERGEN_ALIASES["seafood"]

    recipe = _recipe(ingredients=["white fish fillet", "lemon"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["seafood"]))

    assert not result.is_valid


def test_crustacean_blocks_ambiguous_shellfish_stock() -> None:
    # "shellfish stock" is ambiguous -- it may well contain crustaceans.
    # Allergen ambiguity in this table resolves toward blocking.
    assert "shellfish" in ALLERGEN_ALIASES["crustacean"]

    recipe = _recipe(ingredients=["shellfish stock", "rice noodles"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["crustacean"]))

    assert not result.is_valid


def test_seafood_blocks_crayfish_and_prawn() -> None:
    # Discovered during the composition restructure: hand-copied "seafood"
    # was missing "crayfish" and "prawn" even though they were already in
    # "crustacean" -- a third hand-sync gap beyond the two the restructure
    # was scoped to fix, caught by the seafood>=crustacean invariant above
    # and now fixed structurally (seafood is composed from _CRUSTACEAN).
    crayfish_recipe = _recipe(ingredients=["crayfish", "rice"], allergens=[])
    prawn_recipe = _recipe(ingredients=["prawn crackers", "rice"], allergens=[])

    assert not validate_recipe(crayfish_recipe, _profile(allergies=["seafood"])).is_valid
    assert not validate_recipe(prawn_recipe, _profile(allergies=["seafood"])).is_valid


def test_nuts_blocks_plural_peanuts() -> None:
    # Discovered during the composition restructure: hand-copied "nuts" was
    # missing the plural "peanuts" even though it was already in "peanut" --
    # caught by the nuts>=peanut invariant above and now fixed structurally
    # (nuts is composed from _PEANUT, which is shared with "peanut"/"peanuts").
    assert "peanuts" in ALLERGEN_ALIASES["nuts"]

    recipe = _recipe(ingredients=["mixed peanuts", "raisins"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["nuts"]))

    assert not result.is_valid


# --- 2026-07 confirmed gaps: crawfish/sea bass/marshmallow ------------------
#
# Three more human-confirmed allergen-alias/diet-trap gaps. "crawfish" is
# the common US-regional spelling of "crayfish" (already present) and shares
# no lookalike risk with anything in the corpus. "sea bass" is pinned as the
# full two-word phrase, not bare "bass" (see _FISH's inline comment). Both
# are additions to the base sets (_CRUSTACEAN, _FISH) so "seafood" inherits
# them automatically via composition -- asserted directly below.


def test_crawfish_blocks_shellfish_and_seafood_allergy() -> None:
    tails_recipe = _recipe(ingredients=["crawfish tails", "rice"], allergens=[])
    fat_recipe = _recipe(ingredients=["crawfish fat", "onion"], allergens=[])

    assert not validate_recipe(tails_recipe, _profile(allergies=["shellfish"])).is_valid
    assert not validate_recipe(fat_recipe, _profile(allergies=["shellfish"])).is_valid
    assert not validate_recipe(tails_recipe, _profile(allergies=["seafood"])).is_valid
    assert "crawfish" in ALLERGEN_ALIASES["seafood"]


def test_sea_bass_blocks_fish_and_seafood_allergy() -> None:
    fillet_recipe = _recipe(ingredients=["sea bass fillet", "lemon"], allergens=[])
    filets_recipe = _recipe(ingredients=["filets of fresh sea bass", "butter"], allergens=[])

    assert not validate_recipe(fillet_recipe, _profile(allergies=["fish"])).is_valid
    assert not validate_recipe(filets_recipe, _profile(allergies=["fish"])).is_valid
    assert not validate_recipe(fillet_recipe, _profile(allergies=["seafood"])).is_valid
    assert "sea bass" in ALLERGEN_ALIASES["seafood"]


@pytest.mark.parametrize("diet_type", ["vegan", "vegetarian"])
@pytest.mark.parametrize("ingredient", ["marshmallows", "miniature marshmallows"])
def test_marshmallow_blocks_vegan_and_vegetarian_diet(diet_type: str, ingredient: str) -> None:
    # Standard marshmallows are gelatin-set (animal-derived): a vegetarian
    # violation, not just a vegan one. "marshmallow" is filed in
    # MEAT_ALIASES (not a vegan-only list) precisely so vegetarian inherits
    # it for free via the existing MEAT_ALIASES -> _VEGETARIAN_EXCLUDED_TERMS
    # -> _VEGAN_EXCLUDED_TERMS composition -- see
    # test_worcestershire_still_blocks_vegetarian_diet_after_fish_addition
    # for the same composition pattern applied to a different term.
    recipe = _recipe(ingredients=["sweet potato", ingredient, "pecans"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert not result.is_valid


# --- 2026-07-17 advisor-approved additions: soy-sauce family (wheat), ------
# rennet-set PDO cheeses (vegetarian/vegan/milk), and gelatin/isinglass
# (fish/seafood) ---------------------------------------------------------
#
# See constraint_engine.py's inline comments on _WHEAT ("soy sauce"/"hoisin
# sauce"/"teriyaki sauce"), _RENNET_SET_CHEESES, _DAIRY, and _FISH
# ("gelatin"/"isinglass") for the citations behind each addition below.


def test_soy_sauce_blocks_wheat_and_gluten_but_still_blocks_soy() -> None:
    recipe = _recipe(ingredients=["rice", "soy sauce"], allergens=[], diet_tags=[])

    assert not validate_recipe(recipe, _profile(allergies=["wheat"])).is_valid
    assert not validate_recipe(recipe, _profile(allergies=["gluten"])).is_valid
    assert not validate_recipe(recipe, _profile(diet_type="gluten-free")).is_valid
    # Pre-existing soy-allergen behavior must be unaffected by the wheat addition.
    assert not validate_recipe(recipe, _profile(allergies=["soy"])).is_valid


def test_bare_tamari_blocks_wheat_allergy() -> None:
    # Deliberate, documented fail-closed side effect: app/utils/ingredient_
    # normalizer.py's SYNONYMS maps "tamari" -> "soy sauce", and "soy sauce"
    # is now in _WHEAT (non-GF-labeled tamari can contain wheat, and a bare
    # corpus row cannot prove it's the labeled-GF kind). Pinned here so any
    # future change to that SYNONYMS mapping or to _WHEAT is caught.
    recipe = _recipe(ingredients=["rice", "tamari"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(allergies=["wheat"]))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["hoisin sauce", "teriyaki sauce"])
@pytest.mark.parametrize("allergy", ["wheat", "gluten"])
def test_hoisin_and_teriyaki_sauce_block_wheat_and_gluten(ingredient: str, allergy: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(allergies=[allergy]))

    assert not result.is_valid


@pytest.mark.parametrize(
    "diet_type,ingredient",
    [
        ("vegetarian", "parmesan"),
        ("vegetarian", "parmigiano"),
        ("vegetarian", "pecorino"),
        ("vegetarian", "grana padano"),
        ("vegetarian", "romano cheese"),
        ("vegan", "parmesan"),
        ("vegan", "parmigiano"),
        ("vegan", "pecorino"),
        ("vegan", "grana padano"),
        ("vegan", "romano cheese"),
    ],
)
def test_rennet_set_pdo_cheeses_violate_vegetarian_and_vegan(diet_type: str, ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["cheese", "cheddar"])
def test_generic_cheese_and_cheddar_do_not_violate_vegetarian(ingredient: str) -> None:
    # Generic "cheese"/"cheddar" stay vegetarian-OK: mainstream vegetarian-
    # rennet versions of those are the norm, not the exception -- unlike the
    # PDO-governed names above.
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert result.is_valid


def test_romano_beans_not_blocked_by_vegetarian_diet() -> None:
    # Lookalike guard: "romano bean(s)" is an unrelated legume, never cheese
    # or rennet -- wired identically to the water-chestnut lookalike.
    recipe = _recipe(ingredients=["rice", "romano beans"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert result.is_valid


def test_real_romano_cheese_cannot_hide_behind_romano_beans_in_same_recipe() -> None:
    # Same hiding-attack shape as the chestnut/water-chestnut regression
    # test: a recipe with BOTH the lookalike ("romano beans") AND the real
    # rennet-set cheese ("romano cheese") must still be blocked, on the
    # strength of the real ingredient's own term.
    recipe = _recipe(ingredients=["romano beans", "romano cheese", "rice"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["parmesan", "parmigiano", "pecorino", "romano cheese"])
def test_rennet_set_cheeses_block_milk_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["milk"]))

    assert not result.is_valid


def test_gelatin_blocks_fish_and_seafood_but_not_shellfish_or_crustacean() -> None:
    recipe = _recipe(ingredients=["rice", "gelatin"], allergens=[])

    assert not validate_recipe(recipe, _profile(allergies=["fish"])).is_valid
    assert not validate_recipe(recipe, _profile(allergies=["seafood"])).is_valid
    assert validate_recipe(recipe, _profile(allergies=["shellfish"])).is_valid
    assert validate_recipe(recipe, _profile(allergies=["crustacean"])).is_valid


@pytest.mark.parametrize("diet_type", ["vegetarian", "vegan"])
def test_gelatin_still_violates_vegetarian_and_vegan_diet(diet_type: str) -> None:
    recipe = _recipe(ingredients=["rice", "gelatin"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert not result.is_valid


def test_gelatine_spelling_still_blocks_fish_allergy() -> None:
    # "gelatine" (the British/international spelling) is not a separate set
    # entry -- substring matching against "gelatin" already covers it -- but
    # it is pinned directly so a future refactor of the matching mechanism
    # can't silently drop this spelling.
    recipe = _recipe(ingredients=["rice", "gelatine"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["fish"]))

    assert not result.is_valid


def test_derive_allergen_labels_gelatin_yields_fish_and_seafood() -> None:
    labels = derive_allergen_labels(["gelatin"])

    assert "fish" in labels
    assert "seafood" in labels


def test_derive_allergen_labels_soy_sauce_yields_wheat_gluten_and_soy() -> None:
    labels = derive_allergen_labels(["soy sauce"])

    assert "wheat" in labels
    assert "gluten" in labels
    assert "soy" in labels


def test_water_chestnut_lookalike_tripwire_still_passes_after_romano_addition() -> None:
    # Safe-control tripwire: confirm the pre-existing water-chestnut
    # lookalike guard is unaffected by this change's new _LOOKALIKE_EXCLUSIONS
    # entry ("romano") and new tree-nut/dairy/wheat additions.
    recipe = _recipe(ingredients=["rice", "water chestnut"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert result.is_valid


def test_contains_allergen_soy_sauce_still_true_for_soy_after_wheat_addition() -> None:
    # Direct contains_allergen() sanity check (not just validate_recipe())
    # that adding "soy sauce" to _WHEAT did not disturb its pre-existing
    # membership in _SOY.
    recipe = _recipe(ingredients=["rice", "soy sauce"], allergens=[])

    assert contains_allergen(recipe, ["soy"])


# --- diet_014 remediation: the diet-tag opt-out is removed --------------
# (adjudication_20260718T090522Z.md). A self-asserted `diet_tags` entry can
# no longer bypass the exclusion-vocabulary scan; only the deterministic
# scan decides. These tests pin the DELETION of
# `constraint_engine.violates_diet_type`'s former
# `requested in recipe_tags -> return False` early-return.


@pytest.mark.parametrize(
    "diet_type,ingredient",
    [
        # r_004's literal shape: tagged "vegetarian", carries bare parmesan.
        ("vegetarian", "parmesan"),
        ("vegetarian", "bacon"),
        ("vegan", "butter"),
        ("gluten-free", "all-purpose flour"),
        ("dairy-free", "buttermilk"),
    ],
)
def test_diet_tag_never_loosens_a_dirty_recipe(diet_type: str, ingredient: str) -> None:
    # Tagging a recipe with the requested diet used to short-circuit the
    # scan entirely; a recipe tagged with the requested diet but carrying a
    # disqualifying ingredient must still be REJECTED.
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[diet_type])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert not result.is_valid


@pytest.mark.parametrize(
    "diet_type,ingredients",
    [
        ("vegetarian", ["rice", "spinach"]),
        ("vegan", ["rice", "spinach"]),
        ("gluten-free", ["rice", "spinach"]),
        ("dairy-free", ["rice", "spinach"]),
    ],
)
def test_diet_tag_plus_clean_ingredients_still_admits(diet_type: str, ingredients: list[str]) -> None:
    # Tagged AND ingredient-clean must still be admitted -- the fix must not
    # turn the tag into a second, redundant block on top of the scan.
    recipe = _recipe(ingredients=ingredients, allergens=[], diet_tags=[diet_type])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert result.is_valid


def test_diet_tag_cannot_bypass_fail_loud_for_unsupported_diet_type() -> None:
    # A recipe self-tagged with an unsupported diet_type (e.g. "keto", which
    # UserProfile.diet_type intake rejects, so this exercises
    # violates_diet_type directly) must not let the tag suppress the
    # fail-loud ValueError -- tags were never able to affect this branch,
    # and the deleted opt-out must not have moved it.
    recipe = _recipe(ingredients=["rice", "spinach"], allergens=[], diet_tags=["keto"])

    with pytest.raises(ValueError):
        violates_diet_type(recipe, "keto")


def test_seed_r004_no_longer_has_bare_parmesan_and_passes_vegetarian() -> None:
    # Regression pin for the diet_014 seed fix: r_004's parmesan row was
    # replaced with an explicitly vegetarian cheese, closing the gap the
    # tag opt-out had been hiding.
    recipes = {recipe.recipe_id: recipe for recipe in load_recipes("data/processed/sample_recipes.jsonl")}
    r_004 = recipes["r_004"]

    assert not any(item.name.lower() == "parmesan" for item in r_004.ingredients)
    assert violates_diet_type(r_004, "vegetarian") is False


def test_seed_r010_almond_meal_passes_gluten_free() -> None:
    # Regression pin for the diet_014 seed fix: r_010's "almond flour" row
    # (which tripped the gluten-free scan's "flour" head-noun artifact once
    # the tag opt-out no longer suppressed the scan) was renamed to "almond
    # meal", a term with no gluten alias membership.
    recipes = {recipe.recipe_id: recipe for recipe in load_recipes("data/processed/sample_recipes.jsonl")}
    r_010 = recipes["r_010"]

    assert violates_diet_type(r_010, "gluten-free") is False


# --- A1 revise round, 2026-07-19: vocabulary additions from the diet-leak
# audit exposed by the scraped-archive re-import (bratwurst/bologna/sirloin
# in MEAT_ALIASES; pretzel/pita/orzo in _WHEAT; yoghurt/curd in _DAIRY;
# bean curd in _SOY; two new _LOOKALIKE_EXCLUSIONS entries). See
# docs/BACKLOG.md and constraint_engine.py's inline citations for the full
# rationale per term.


@pytest.mark.parametrize("ingredient", ["bratwursts", "sirloin tip roast", "bologna"])
def test_new_meat_terms_violate_vegetarian_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


def test_bratwurst_also_violates_vegan_diet() -> None:
    recipe = _recipe(ingredients=["rice", "bratwursts"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegan"))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["pretzels, finely crushed", "pita pockets", "orzo"])
def test_new_wheat_terms_block_gluten_and_wheat_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])

    assert contains_allergen(recipe, ["gluten"])
    assert contains_allergen(recipe, ["wheat"])


@pytest.mark.parametrize("ingredient", ["natural yoghurt", "lemon curd"])
def test_new_dairy_terms_block_dairy_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])

    assert contains_allergen(recipe, ["dairy"])


def test_bean_curd_is_soy_not_dairy() -> None:
    # Lookalike guard: "bean curd" (tofu) must never trip the new "curd"
    # dairy term, must never violate dairy-free, and must correctly trip
    # the SOY allergen (added to _SOY directly, not via lookalike).
    recipe = _recipe(ingredients=["rice", "bean curd"], allergens=[], diet_tags=[])

    assert not contains_allergen(recipe, ["dairy"])
    assert not contains_allergen(recipe, ["milk"])
    assert violates_diet_type(recipe, "dairy-free") is False
    assert contains_allergen(recipe, ["soy"])


def test_real_dairy_curd_cannot_hide_behind_bean_curd_in_same_recipe() -> None:
    # Same hiding-attack shape as the chestnut/romano regression tests: a
    # recipe with BOTH the lookalike ("bean curd") AND a real dairy curd
    # ingredient ("cheese curds") must still be blocked for a dairy
    # allergy, on the strength of the real ingredient's own term.
    recipe = _recipe(ingredients=["bean curd", "cheese curds", "rice"], allergens=[])

    assert contains_allergen(recipe, ["dairy"])


def test_pitaya_not_blocked_by_gluten_allergy() -> None:
    # Lookalike guard: "pitaya" (dragon fruit) is genuinely gluten-free and
    # botanically unrelated to "pita" (wheat flatbread).
    recipe = _recipe(ingredients=["rice", "pitaya"], allergens=[])

    assert not contains_allergen(recipe, ["gluten"])


def test_pita_bread_still_blocked_by_gluten_allergy() -> None:
    recipe = _recipe(ingredients=["rice", "pita bread"], allergens=[])

    assert contains_allergen(recipe, ["gluten"])


# --- Closing-verdict cure, 2026-07-19: diet_023 TRUE_VIOLATION
# (adjudication_20260719T083748Z.md) -- Kellogg's Rice Krispies contain
# barley malt flavoring, undetectable by the pre-cure gluten vocabulary.


@pytest.mark.parametrize("ingredient", ["Rice Krispies", "Post Grape-Nuts cereal"])
def test_krispies_and_cereal_block_gluten_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])

    assert contains_allergen(recipe, ["gluten"])


def test_rice_krispies_does_not_block_wheat_allergy() -> None:
    # "krispies"/"cereal" are barley-malt vehicles, added only at the
    # "gluten" ALLERGEN_ALIASES composition -- NOT in _WHEAT itself, so a
    # wheat-specific allergy must stay unaffected.
    recipe = _recipe(ingredients=["rice", "Rice Krispies"], allergens=[])

    assert not contains_allergen(recipe, ["wheat"])


def test_enchilada_sauce_blocks_peanut_allergy() -> None:
    recipe = _recipe(ingredients=["rice", "enchilada sauce (Mild or Hot, your choice)"], allergens=[])

    assert contains_allergen(recipe, ["peanut"])
    assert contains_allergen(recipe, ["peanuts"])
    assert contains_allergen(recipe, ["nuts"])


# --- Direction-aware lookalike matching fix, 2026-07-19 (docs/BACKLOG.md) ---
#
# `_recipe_contains_any_term`'s bidirectional substring matching (`term ==
# recipe_term or term in recipe_term or recipe_term in term`) had an unsafe
# REVERSE arm: a bare ingredient word could match merely because it was a
# substring of a longer, unrelated compound term (bare "pepper" matching
# "pepperoni"; bare "soy" matching "soy sauce"). This is now one-directional
# (`_any_term_matches`: `term in candidate`, never the reverse) -- these
# tests pin the motivating cases from the task spec, plus the four new
# precise compound gluten terms this fix enables.


def test_bare_soy_does_not_trip_gluten_filter_but_still_trips_soy_allergen() -> None:
    # "soy" reverse-matched _WHEAT's "soy sauce" entry before this fix
    # ("soy" in "soy sauce" is True), wrongly failing gluten-free/wheat for a
    # plain soybean ingredient with no wheat content at all. Soy itself must
    # still trip a soy allergy -- "soy" is a direct _SOY member.
    recipe = _recipe(ingredients=["rice", "soy"], allergens=[], diet_tags=[])

    assert not contains_allergen(recipe, ["gluten"])
    assert not contains_allergen(recipe, ["wheat"])
    assert not violates_diet_type(recipe, "gluten-free")
    assert contains_allergen(recipe, ["soy"])


def test_bare_pepper_still_passes_vegetarian() -> None:
    # The bug's original motivating case: bare "pepper" (bell pepper/ground
    # black pepper) is not meat and must never fail vegetarian just because
    # it is a substring of "pepperoni".
    recipe = _recipe(ingredients=["rice", "pepper"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert result.is_valid


def test_pepperoni_alone_still_fails_vegetarian() -> None:
    recipe = _recipe(ingredients=["rice", "pepperoni"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


def test_pepperoni_and_bare_pepper_together_still_fails_vegetarian() -> None:
    # A recipe carrying BOTH the real meat ("pepperoni") and the unrelated
    # bare word ("pepper") must still fail, on the strength of "pepperoni"'s
    # own (forward) match -- removing the reverse arm must not weaken this.
    recipe = _recipe(ingredients=["pepperoni", "pepper", "rice"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


@pytest.mark.parametrize(
    "ingredient",
    ["corn flakes, crumbled", "1/2 cup Post Toasties", "Rice Krispies", "Post Grape-Nuts cereal"],
)
def test_new_precise_brand_cereal_terms_block_gluten_allergy(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])

    assert contains_allergen(recipe, ["gluten"])


@pytest.mark.parametrize("ingredient", ["corn", "rice", "grapes"])
def test_bare_corn_flakes_lookalike_words_do_not_block_gluten_allergy(ingredient: str) -> None:
    # The exact hazard the new compound terms ("corn flakes", "rice
    # krispies", "grape-nuts") would have reintroduced under the OLD
    # bidirectional matching: bare "corn"/"rice"/"grapes" must never reverse-
    # match into these longer compound terms.
    recipe = _recipe(ingredients=["olive oil", ingredient], allergens=[])

    assert not contains_allergen(recipe, ["gluten"])


def test_bare_nuts_ingredient_does_not_block_gluten_allergy() -> None:
    # "nuts" is genuinely, definitionally a tree-nut/peanut ingredient (see
    # test_bare_nuts_ingredient_blocks_tree_nut_and_peanut_allergy below),
    # but must never be confused for gluten via "grape-nuts".
    recipe = _recipe(ingredients=["olive oil", "nuts"], allergens=[])

    assert not contains_allergen(recipe, ["gluten"])


def test_bare_nuts_ingredient_blocks_tree_nut_and_peanut_allergy() -> None:
    # Compensating addition for a real reverse-arm-removal loss: a bare,
    # unqualified "nuts" ingredient (16 real corpus recipes, e.g. Applesauce
    # Cake, Deep Dark Secret) was accidentally caught pre-fix via the
    # reverse arm (bare "nut" is a substring of every compound tree-nut
    # term). A plain ALLERGEN_ALIASES substring term for "nut"/"nuts" would
    # be unsafe (it would forward-match "butternut squash", "water
    # chestnut", "nutmeg", "coconut", ...) -- see contains_allergen's
    # _BARE_NUT_WORD word-boundary check, which catches this precisely
    # instead.
    recipe = _recipe(ingredients=["flour", "nuts"], allergens=[])

    assert contains_allergen(recipe, ["tree nut"])
    assert contains_allergen(recipe, ["peanut"])
    assert contains_allergen(recipe, ["nuts"])


@pytest.mark.parametrize(
    "allergy",
    ["tree nuts", "Tree Nuts", "nut"],
)
def test_bare_nuts_ingredient_blocks_free_text_allergy_spelling_variants(allergy: str) -> None:
    # UNDER-BLOCK REGRESSION FIX (direction-aware lookalike matching, revise
    # round 1): the prior version of the bare-nut compensation matched the
    # RAW, unnormalized allergy string against a hardcoded literal frozenset
    # ({"tree nut", "nuts", "peanut", "peanuts"}), so it only fired for
    # those exact spellings -- missing plural "tree nuts", case variants
    # ("Tree Nuts"), and the bare singular "nut", even though
    # UserProfile.allergies is genuine free text with no upstream
    # canonicalization (app/schemas/user.py) and real users type all of
    # these. Confirmed as a real regression by advisor review reproducing
    # directly against the pre-fix baseline (4a97b80~1):
    #   bare "nuts" + allergies=["tree nut"]  -> True  (already correct)
    #   bare "nuts" + allergies=["tree nuts"] -> False (WRONG, pre-fix)
    #   bare "nuts" + allergies=["Tree Nuts"] -> False (WRONG, pre-fix)
    #   bare "nuts" + allergies=["nut"]       -> False (WRONG, pre-fix)
    # Each of the three cases here must now return True. See
    # test_bare_nuts_ingredient_blocks_tree_nut_and_peanut_allergy above for
    # the already-passing "tree nut"/"nuts" spellings this test deliberately
    # does not re-cover.
    recipe = _recipe(ingredients=["flour", "nuts"], allergens=[])

    assert contains_allergen(recipe, [allergy])


@pytest.mark.parametrize(
    "ingredient",
    ["butternut squash", "water chestnut", "chestnut puree", "nutmeg", "coconut, flaked", "walnut", "peanuts"],
)
def test_bare_nut_word_check_does_not_over_block_unrelated_or_already_covered_ingredients(ingredient: str) -> None:
    # The word-boundary check must never match "nut"/"nuts" as a mere
    # SUBSTRING of a longer, unrelated word -- that would reintroduce the
    # exact kind of over-broad match this whole fix exists to remove, just
    # in the forward direction. "walnut"/"peanuts" are included to confirm
    # this check adds nothing on top of their own pre-existing, correct
    # explicit-term coverage (both must still be blocked -- via their own
    # terms, not this check).
    #
    # Deliberately checks the "tree nut" and "peanut" allergy keys only, not
    # "nuts": requesting allergy=["nuts"] independently normalizes the
    # ALLERGY NAME ITSELF ("nuts" -> "nut", via the same pluralization rule
    # normalize_ingredient applies to ingredient names) into a bare "nut"
    # matching term via `_expand_allergen_terms` -- a PRE-EXISTING,
    # unrelated bug (confirmed present on main before this task's changes)
    # that already over-blocks "nutmeg"/"butternut squash"/etc. for a
    # "nuts"-allergy request regardless of this fix. See "Noticed, not
    # fixed" in this task's report / docs/BACKLOG.md -- out of scope here.
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])
    # "chestnut puree" is a REAL tree nut (chestnut is a direct _TREE_NUT
    # member) and must stay blocked -- only "water chestnut" (the lookalike)
    # must not be.
    expected_tree_nut_block = ingredient in {"walnut", "chestnut puree"}

    assert contains_allergen(recipe, ["tree nut"]) is expected_tree_nut_block
    assert contains_allergen(recipe, ["peanut"]) is (ingredient == "peanuts")


def test_bare_butter_does_not_block_peanut_allergy() -> None:
    # False positive correctly removed: bare "butter" (dairy) is not peanut
    # butter, and reverse-matched "peanut butter" before this fix.
    recipe = _recipe(ingredients=["flour", "butter"], allergens=[])

    assert not contains_allergen(recipe, ["peanut"])


def test_bare_sage_does_not_block_vegetarian_or_vegan_diet() -> None:
    # False positive correctly removed: bare "sage" (herb) reverse-matched
    # "sausage" before this fix.
    recipe = _recipe(ingredients=["rice", "sage"], allergens=[], diet_tags=[])

    assert not violates_diet_type(recipe, "vegetarian")
    assert not violates_diet_type(recipe, "vegan")


def test_bare_ham_does_not_block_gluten_allergy() -> None:
    # False positive correctly removed: bare "ham" (a substring of "graham"
    # cracker) reverse-matched "graham cracker" before this fix.
    recipe = _recipe(ingredients=["rice", "ham"], allergens=[])

    assert not contains_allergen(recipe, ["gluten"])


# --- Systematic ground-truth-vs-production vocabulary diff closure,
# 2026-07-20 (docs/BACKLOG.md) -- 16 meat/poultry/fish terms added to
# MEAT_ALIASES (anchovies was already a no-op: normalize_ingredient
# depluralizes it to "anchovy", already a _FISH member) and 9 dairy terms
# added to _DAIRY, all confirmed against scripts/audit_diet_leaks.py's
# independent ground truth. See constraint_engine.py's inline citations for
# the per-term sourcing and corpus-hit counts.


@pytest.mark.parametrize(
    "ingredient",
    [
        "beef brisket",
        "salami",
        "grouper",
        "mackerel",
        "small meatballs",
        "tilapia",
        "capon",
        "pheasant",
        "quail",
        "tripe",
        "venison",
    ],
)
def test_new_meat_vocabulary_blocks_vegetarian_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


def test_anchovies_plural_already_a_no_op_still_blocks_vegetarian() -> None:
    # Confirms the task-spec claim directly: "anchovies" is NOT a separate
    # MEAT_ALIASES entry -- normalize_ingredient depluralizes it to
    # "anchovy", already a member of ALLERGEN_ALIASES["fish"], which already
    # flows into _VEGETARIAN_EXCLUDED_TERMS. This is a pre-existing behavior
    # pin, not a new addition.
    recipe = _recipe(ingredients=["rice", "whole anchovies"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


@pytest.mark.parametrize("diet_type", ["vegetarian", "vegan"])
@pytest.mark.parametrize("ingredient", ["squid", "squid rings", "calamari", "octopus"])
def test_cephalopod_mollusks_block_vegetarian_and_vegan_diet(diet_type: str, ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type=diet_type))

    assert not result.is_valid


@pytest.mark.parametrize("ingredient", ["squid", "calamari", "octopus"])
def test_cephalopod_mollusks_also_block_shellfish_and_seafood_allergy(ingredient: str) -> None:
    # Dual taxonomy membership: these are cephalopod mollusks (this codebase
    # already treats clam/mussel/oyster/scallop as _MOLLUSK, beyond the
    # narrower FALCPA "molluscs" species list), so they must trip BOTH the
    # vegetarian/vegan diet-type check (via MEAT_ALIASES, tested above) AND
    # the shellfish/seafood allergen check (via _MOLLUSK) independently.
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])

    assert contains_allergen(recipe, ["shellfish"])
    assert contains_allergen(recipe, ["seafood"])


def test_caviar_blocks_vegetarian_and_vegan_diet() -> None:
    recipe = _recipe(ingredients=["rice", "caviar"], allergens=[], diet_tags=[])

    assert not validate_recipe(recipe, _profile(diet_type="vegetarian")).is_valid
    assert not validate_recipe(recipe, _profile(diet_type="vegan")).is_valid


def test_caviar_also_blocks_fish_and_seafood_allergy() -> None:
    # Dual membership: caviar is fish roe, added to both MEAT_ALIASES (diet
    # path, tested above) and ALLERGEN_ALIASES["fish"] (allergy path) --
    # mirrors the existing "gelatin"/"worcestershire" dual-membership
    # pattern.
    recipe = _recipe(ingredients=["rice", "caviar"], allergens=[])

    assert contains_allergen(recipe, ["fish"])
    assert contains_allergen(recipe, ["seafood"])


@pytest.mark.parametrize(
    "ingredient",
    ["gruyere cheese", "provolone cheese", "creme fraiche", "custard powder", "brie cheese", "kefir", "camembert"],
)
def test_new_dairy_vocabulary_blocks_dairy_allergy_and_dairy_free_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[])

    assert contains_allergen(recipe, ["dairy"])
    assert violates_diet_type(recipe, "dairy-free") is True


def test_gruyere_blocks_both_dairy_allergy_and_dairy_free_diet() -> None:
    # Explicit dual-check example requested by the task spec's acceptance
    # criteria: one dairy term proven to trigger both paths independently.
    recipe = _recipe(ingredients=["rice", "gruyere cheese"], allergens=[], diet_tags=[])

    assert contains_allergen(recipe, ["dairy"])
    assert not validate_recipe(recipe, _profile(diet_type="dairy-free")).is_valid


# --- "capon"/"caponata" lookalike carve-out ---------------------------------
# "capon" (a castrated rooster, poultry) is a literal substring of
# "caponata" (a vegetarian eggplant dish, unrelated). Same water-chestnut-
# class mechanism, wired identically.


def test_caponata_not_blocked_by_vegetarian_diet() -> None:
    recipe = _recipe(ingredients=["rice", "caponata"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert result.is_valid


def test_bare_capon_still_blocks_vegetarian_diet() -> None:
    recipe = _recipe(ingredients=["rice", "capon"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


def test_real_capon_cannot_hide_behind_caponata_in_same_recipe() -> None:
    # Per-ingredient-term semantics: a recipe with BOTH the lookalike
    # ("caponata") AND a real capon ingredient must still be blocked, on the
    # strength of the real ingredient's own term.
    recipe = _recipe(ingredients=["caponata", "capon", "rice"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


# --- "tripe"/"striped" lookalike carve-out ----------------------------------
# "tripe" is a literal substring of "striped" (t-r-i-p-e inside
# s-t-r-i-p-e-d). Added preemptively alongside "tripe" itself so this
# landmine never goes live even for a day.


@pytest.mark.parametrize("ingredient", ["striped bass", "striped watermelon"])
def test_striped_ingredients_not_blocked_by_vegetarian_diet_via_tripe(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert result.is_valid


def test_bare_tripe_still_blocks_vegetarian_diet() -> None:
    recipe = _recipe(ingredients=["rice", "tripe"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


def test_real_tripe_cannot_hide_behind_striped_in_same_recipe() -> None:
    recipe = _recipe(ingredients=["striped bass", "tripe", "rice"], allergens=[], diet_tags=[])
    result = validate_recipe(recipe, _profile(diet_type="vegetarian"))

    assert not result.is_valid


# --- "brie"/"o'brien" lookalike carve-out (self-discovered during this
# task's over-block measurement, not part of the original task-spec diff) --
# "brie" is a literal substring of "o'brien" (b-r-i-e inside o-'-b-r-i-e-n),
# a real corpus ingredient ("O'Brien potatoes", no dairy content).


@pytest.mark.parametrize("ingredient", ["o'brien frozen potatoes", "obrien potatoes"])
def test_obrien_potatoes_not_blocked_by_dairy_allergy_or_dairy_free_diet(ingredient: str) -> None:
    recipe = _recipe(ingredients=["rice", ingredient], allergens=[], diet_tags=[])

    assert not contains_allergen(recipe, ["dairy"])
    assert violates_diet_type(recipe, "dairy-free") is False


def test_bare_brie_still_blocks_dairy_allergy_and_dairy_free_diet() -> None:
    recipe = _recipe(ingredients=["rice", "brie cheese"], allergens=[], diet_tags=[])

    assert contains_allergen(recipe, ["dairy"])
    assert violates_diet_type(recipe, "dairy-free") is True


def test_real_brie_cannot_hide_behind_obrien_potatoes_in_same_recipe() -> None:
    recipe = _recipe(ingredients=["o'brien potatoes", "brie cheese", "rice"], allergens=[])

    assert contains_allergen(recipe, ["dairy"])
