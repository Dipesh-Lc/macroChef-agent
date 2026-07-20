import pytest

from app.schemas.inventory import ConfirmedIngredient
from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.schemas.recommendation import TasteProfile
from app.schemas.user import MacroTargets, UserProfile
from app.services.nutrition_scorer import (
    macro_fit_score,
    pantry_match_score,
    preference_score,
    score_recipe,
)


def _grounded(**per_serving) -> RecipeNutrition:
    macros = FoodMacros(**per_serving)
    return RecipeNutrition(
        status=GroundingStatus.GROUNDED,
        servings=1,
        total=macros,
        per_serving=macros,
        coverage=1.0,
    )


def _recipe(**kwargs) -> Recipe:
    defaults = {
        "recipe_id": "r",
        "title": "Macro Recipe",
        "ingredients": ["chicken breast", "rice", "spinach", "bell pepper"],
        "instructions": ["Cook."],
        "allergens": [],
        "diet_tags": [],
        "cook_time_min": 20,
        # Self-reported tag macros -- realistic filler only. The scorer must
        # never read these (see test_macro_fit_ignores_tag_macros_*): the
        # perfect/poor-match tests below rely solely on `nutrition`.
        "calories": 500,
        "protein_g": 40,
        "carbs_g": 50,
        "fat_g": 15,
        "fiber_g": 8,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


def test_scores_perfect_macro_match_high() -> None:
    recipe = _recipe(nutrition=_grounded(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8))
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) == 1.0


def test_scores_poor_macro_match_lower() -> None:
    # Tag calories are left at the "perfect" 500/40/50/15/8 filler from
    # _recipe() defaults -- the computed nutrition below is the mismatched
    # one, so this only passes if the scorer reads nutrition, not tags.
    recipe = _recipe(
        nutrition=_grounded(calories=900, protein_g=10, carbs_g=120, fat_g=45, fiber_g=2)
    )
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) < 0.5


def test_macro_fit_neutral_when_ungrounded() -> None:
    # Tag macros are a perfect match for targets, but with no `nutrition` at
    # all the recipe must score neutral, never off the self-reported tag.
    recipe = _recipe(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) == 0.5


def test_macro_fit_neutral_when_partial() -> None:
    partial = RecipeNutrition(
        status=GroundingStatus.PARTIAL,
        servings=1,
        total=FoodMacros(calories=300, protein_g=20, carbs_g=30, fat_g=8, fiber_g=4),
        per_serving=FoodMacros(calories=300, protein_g=20, carbs_g=30, fat_g=8, fiber_g=4),
        ungrounded_ingredients=["mystery sauce"],
        coverage=0.5,
    )
    recipe = _recipe(nutrition=partial)
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    # PARTIAL undercounts (only sums grounded ingredients) -- trusting it here
    # would read as falsely low-calorie, so it must stay neutral like UNGROUNDED.
    assert macro_fit_score(recipe, targets) == 0.5


def test_macro_fit_neutral_when_grounded_but_flagged() -> None:
    # A trust-demoting flag (see grounding_job.DEMOTING_FLAG_IMPLAUSIBLE_KCAL)
    # must demote scoring to neutral even when status is GROUNDED -- an
    # implausible computed value is not more trustworthy just because every
    # ingredient happened to ground. Tag macros are a perfect match for
    # targets to prove the scorer isn't accidentally falling back to them.
    flagged = _grounded(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)
    flagged.flags.append("implausible_kcal_per_serving")
    recipe = _recipe(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8, nutrition=flagged)
    targets = MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8)

    assert macro_fit_score(recipe, targets) == 0.5


def test_calculates_pantry_match_correctly() -> None:
    # All four ingredients are bare name-only strings (no amount/unit), so
    # none of them can resolve to grams -- this is the pure count-fallback
    # path (mass_coverage == 0.0), and the score is identical to the old
    # name-count formula: 2 used / 4 total = 0.5.
    recipe = _recipe()
    inventory = [
        ConfirmedIngredient(name="chicken breast"),
        ConfirmedIngredient(name="rice"),
    ]

    score, used, missing, mass_coverage = pantry_match_score(recipe, inventory)

    assert score == 0.5
    assert used == ["chicken breast", "rice"]
    assert missing == ["spinach", "bell pepper"]
    assert mass_coverage == 0.0


def test_pantry_used_missing_amount_aware() -> None:
    # Enough chicken, but short on rice -> rice counts as missing despite being present.
    # Both ingredients are gram-denominated (fully convertible), so this is the
    # pure mass-weighted path: 500 g used chicken / 800 g total = 0.625, NOT
    # the old 1/2 == 0.5 name-count value.
    recipe = _recipe(ingredients=["500 g chicken breast", "300 g rice"])
    inventory = [
        ConfirmedIngredient(name="chicken breast", amount=600, unit="g"),
        ConfirmedIngredient(name="rice", amount=100, unit="g"),
    ]

    score, used, missing, mass_coverage = pantry_match_score(recipe, inventory)

    assert used == ["chicken breast"]
    assert missing == ["rice"]
    assert score == 0.625
    assert mass_coverage == 1.0


def test_pantry_mass_weighting_disagrees_with_old_name_count() -> None:
    # Three cheap 5 g spices are present (would dominate the old name-count
    # score: 3/4 == 0.75), but the recipe's one heavy 500 g protein is
    # missing. Mass-weighting must score this LOW, not high -- this is the
    # exact bug B5 fixes.
    recipe = _recipe(
        ingredients=["500 g chicken breast", "5 g salt", "5 g pepper", "5 g garlic powder"]
    )
    inventory = [
        ConfirmedIngredient(name="salt", amount=5, unit="g"),
        ConfirmedIngredient(name="pepper", amount=5, unit="g"),
        ConfirmedIngredient(name="garlic powder", amount=5, unit="g"),
    ]

    score, used, missing, mass_coverage = pantry_match_score(recipe, inventory)

    old_name_count_score = len(used) / len(recipe.ingredients)
    assert old_name_count_score == 0.75
    assert mass_coverage == 1.0
    assert missing == ["chicken breast"]
    # 15 g used / 515 g total.
    assert score == pytest.approx(15 / 515)
    assert score < old_name_count_score


def test_pantry_match_fallback_when_nothing_convertible() -> None:
    # No ingredient has an amount at all -> nothing resolves to grams, so the
    # score must fall all the way back to the old pure name-count formula,
    # and mass_coverage must report 0.0 so callers can see the score isn't
    # actually mass-grounded.
    recipe = _recipe(ingredients=["chicken breast", "rice", "spinach"])
    inventory = [ConfirmedIngredient(name="chicken breast"), ConfirmedIngredient(name="rice")]

    score, used, missing, mass_coverage = pantry_match_score(recipe, inventory)

    assert mass_coverage == 0.0
    assert score == pytest.approx(2 / 3)
    assert used == ["chicken breast", "rice"]
    assert missing == ["spinach"]


def test_pantry_match_mixed_convertible_and_unconvertible() -> None:
    # Two gram-denominated ingredients (chicken used, rice missing) blend with
    # two bare unconvertible ones (spinach used, bell pepper missing).
    # Convertible pool: 400 g used / 500 g total = 0.8, weight 2/4 = 0.5.
    # Unconvertible pool: 1 used / 2 total = 0.5, weight 2/4 = 0.5.
    # Blended: 0.5*0.8 + 0.5*0.5 = 0.65.
    recipe = _recipe(
        ingredients=["400 g chicken breast", "100 g rice", "spinach", "bell pepper"]
    )
    inventory = [
        ConfirmedIngredient(name="chicken breast", amount=400, unit="g"),
        ConfirmedIngredient(name="spinach"),
    ]

    score, used, missing, mass_coverage = pantry_match_score(recipe, inventory)

    assert used == ["chicken breast", "spinach"]
    assert missing == ["rice", "bell pepper"]
    assert mass_coverage == 0.5
    assert score == pytest.approx(0.65)


def test_score_recipe_returns_breakdown() -> None:
    recipe = _recipe(nutrition=_grounded(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8))
    inventory = [ConfirmedIngredient(name="chicken breast"), ConfirmedIngredient(name="rice")]
    profile = UserProfile(
        user_id="u",
        macro_targets=MacroTargets(calories=500, protein_g=40, carbs_g=50, fat_g=15, fiber_g=8),
        max_cook_time_min=30,
    )

    score = score_recipe(recipe, inventory, profile)

    assert score.final_score > 0.6
    assert score.macro_fit_score == 1.0


# ---------------------------------------------------------------------------
# Phase 3 (visible personalization loop): the GENERALIZING taste-profile
# nudge in preference_score. Distinct from the exact-recipe-id checks (the
# `liked_recipe_ids`/`disliked_recipe_ids` params, tested implicitly above
# via score_recipe) -- this fires on a recipe the user has never rated,
# purely from ingredient/cuisine patterns in `taste_profile`. Must stay
# small and bounded (never overriding an explicit static cuisine match or an
# exact-recipe-id signal) -- see app.services.nutrition_scorer.preference_
# score's inline rationale.
# ---------------------------------------------------------------------------


def test_taste_profile_none_has_no_effect() -> None:
    recipe = _recipe()
    profile = UserProfile(user_id="u", macro_targets=MacroTargets(), max_cook_time_min=None)

    assert preference_score(recipe, profile, taste_profile=None) == 0.5


def test_taste_profile_avoided_ingredient_lowers_score_by_bounded_amount() -> None:
    recipe = _recipe()  # ingredients: chicken breast, rice, spinach, bell pepper
    profile = UserProfile(user_id="u", macro_targets=MacroTargets(), max_cook_time_min=None)
    taste_profile = TasteProfile(avoided_ingredients=["chicken breast", "rice"])

    score = preference_score(recipe, profile, taste_profile=taste_profile)

    # Both "chicken breast" and "rice" match the avoided set, but the penalty
    # applies once, not per match -- bounded at -0.05, not -0.10+.
    assert score == pytest.approx(0.45)


def test_taste_profile_drifted_cuisine_boosts_score_by_bounded_amount() -> None:
    recipe = _recipe(cuisine="Italian")
    profile = UserProfile(user_id="u", macro_targets=MacroTargets(), max_cook_time_min=None)
    taste_profile = TasteProfile(preferred_cuisines=["Italian"])

    score = preference_score(recipe, profile, taste_profile=taste_profile)

    assert score == pytest.approx(0.55)


def test_taste_profile_drift_does_not_stack_with_static_cuisine_match() -> None:
    # cuisine_preference already matches (static +0.2) -- the drifted-cuisine
    # nudge must not ALSO add its +0.05 on top of the same signal.
    recipe = _recipe(cuisine="Italian")
    profile = UserProfile(user_id="u", macro_targets=MacroTargets(), max_cook_time_min=None)
    taste_profile = TasteProfile(preferred_cuisines=["Italian"])

    score = preference_score(
        recipe, profile, cuisine_preference="Italian", taste_profile=taste_profile
    )

    assert score == pytest.approx(0.7)


def test_taste_profile_never_overrides_explicit_dislike() -> None:
    # An exact-recipe dislike (-0.2) must still dominate even when the same
    # recipe also happens to match a drifted-cuisine preference (+0.05).
    recipe = _recipe(cuisine="Italian")
    profile = UserProfile(user_id="u", macro_targets=MacroTargets(), max_cook_time_min=None)
    taste_profile = TasteProfile(preferred_cuisines=["Italian"])

    score = preference_score(
        recipe,
        profile,
        disliked_recipe_ids={recipe.recipe_id},
        taste_profile=taste_profile,
    )

    assert score == pytest.approx(0.35)
    assert score < 0.5
