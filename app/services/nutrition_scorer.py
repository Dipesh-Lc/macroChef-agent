from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import RecipeScore
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.nutrition_view import trusted_per_serving
from app.services.procurement_service import analyze_ingredients
from app.utils.unit_converter import to_grams


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def pantry_match_score(
    recipe: Recipe, inventory: list[ConfirmedIngredient]
) -> tuple[float, list[str], list[str], float]:
    """Fraction of the recipe the pantry covers, weighted by ingredient MASS
    rather than ingredient count.

    Why: pure name-count (the old formula) scores a recipe as "mostly covered"
    the moment most of its ingredient ROWS are on hand, even if the one row
    that's missing is 500 g of the recipe's main protein and the rest are
    5 g pinches of spice. Weighting by grams (via `unit_converter.to_grams`,
    which never guesses -- it returns None rather than fabricate a mass) fixes
    that.

    Design decision -- honest mass/count hybrid, not fabricated mass (B5):
    `to_grams` can't resolve every ingredient (no amount, or no known
    density/piece-weight -- common in this corpus per A3's terminal-outcome
    tally). We must not silently drop unconvertible ingredients (that biases
    the score toward recipes with MORE ungroundable ingredients, since a
    dropped ingredient can never count against the score) and must not invent
    a mass for them either. Instead the ingredient list splits into two pools,
    each scored honestly on its own terms:
      - convertible pool: grams-used / grams-total (the actual fix)
      - unconvertible pool: count-used / count-total (the OLD formula,
        preserved verbatim for exactly the ingredients mass can't speak to)
    and the two pool scores are blended, weighted by each pool's share of the
    recipe's ingredient COUNT. This degrades gracefully to the old pure
    name-count formula when nothing converts (mass_coverage == 0.0) and to
    pure mass-weighting when everything does (mass_coverage == 1.0), without
    ever guessing a mass. This mirrors nutrition_view's grounded/partial
    honesty pattern (`RecipeNutrition.coverage`): score only what's actually
    known, and expose how much of the score rests on real data (here,
    `mass_coverage`) rather than silently blending fabricated numbers in.

    Returns (score, used_names, missing_names, mass_coverage). `used`/`missing`
    keep the exact same meaning as before (see `procurement_service
    .split_used_and_missing`) -- only the score's weighting changed.
    """
    results = analyze_ingredients(recipe, inventory)
    if not recipe.ingredients:
        return 0.0, [], [], 0.0

    used: list[str] = []
    missing: list[str] = []
    mass_total = 0.0
    mass_used = 0.0
    count_total = 0
    count_used = 0
    convertible_count = 0

    for ingredient, result in zip(recipe.ingredients, results):
        is_used = result.status in ("satisfied", "present_uncompared")
        (used if is_used else missing).append(result.name)

        grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
        if grams is not None:
            convertible_count += 1
            mass_total += grams
            if is_used:
                mass_used += grams
        else:
            count_total += 1
            if is_used:
                count_used += 1

    total_ingredients = len(recipe.ingredients)
    mass_coverage = convertible_count / total_ingredients

    mass_subscore = (mass_used / mass_total) if mass_total > 0 else None
    count_subscore = (count_used / count_total) if count_total > 0 else None

    if mass_subscore is None and count_subscore is None:
        # Degenerate: every convertible ingredient had amount 0 and there were
        # no unconvertible ones either. Shouldn't happen with real recipe
        # data, but don't divide by zero.
        score = 0.0
    elif mass_subscore is None:
        score = count_subscore
    elif count_subscore is None:
        score = mass_subscore
    else:
        weight_mass = convertible_count / total_ingredients
        weight_count = count_total / total_ingredients
        score = weight_mass * mass_subscore + weight_count * count_subscore

    return score, used, missing, mass_coverage


def macro_fit_score(recipe: Recipe, targets: MacroTargets) -> float:
    # Only a fully GROUNDED recipe's computed macros are trusted here (see
    # app.services.nutrition_view) -- PARTIAL undercounts, and UNGROUNDED has
    # nothing to score, so both fall back to the neutral 0.5 rather than
    # scoring against the recipe's self-reported tag macros.
    macros = trusted_per_serving(recipe)
    if macros is None:
        return 0.5

    fields = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g"]
    errors: list[float] = []
    for field in fields:
        target = getattr(targets, field)
        actual = getattr(macros, field)
        if target is None or target <= 0:
            continue
        errors.append(abs(actual - target) / target)

    if not errors:
        return 0.5

    average_error = sum(errors) / len(errors)
    return clamp(1.0 - average_error)


def time_score(recipe: Recipe, max_cook_time: int | None) -> float:
    if recipe.cook_time_min is None:
        return 0.0
    if not max_cook_time:
        return 0.8
    if recipe.cook_time_min > max_cook_time:
        return 0.0
    if recipe.cook_time_min <= max_cook_time * 0.75:
        return 1.0
    return clamp(1.0 - ((recipe.cook_time_min - max_cook_time * 0.75) / (max_cook_time * 0.25)) * 0.4)


def preference_score(
    recipe: Recipe,
    user_profile: UserProfile,
    cuisine_preference: str | None = None,
    liked_recipe_ids: set[str] | None = None,
    disliked_recipe_ids: set[str] | None = None,
) -> float:
    score = 0.5
    preferred = cuisine_preference or (
        user_profile.preferred_cuisines[0] if user_profile.preferred_cuisines else None
    )
    if preferred and recipe.cuisine and recipe.cuisine.lower() == preferred.lower():
        score += 0.2
    if liked_recipe_ids and recipe.recipe_id in liked_recipe_ids:
        score += 0.1
    if disliked_recipe_ids and recipe.recipe_id in disliked_recipe_ids:
        score -= 0.2
    return clamp(score)


def score_recipe(
    recipe: Recipe,
    inventory: list[ConfirmedIngredient],
    user_profile: UserProfile,
    cuisine_preference: str | None = None,
    liked_recipe_ids: set[str] | None = None,
    disliked_recipe_ids: set[str] | None = None,
) -> RecipeScore:
    pantry_score, used, missing, mass_coverage = pantry_match_score(recipe, inventory)
    macro_score = macro_fit_score(recipe, user_profile.macro_targets)
    cook_score = time_score(recipe, user_profile.max_cook_time_min)
    pref_score = preference_score(
        recipe, user_profile, cuisine_preference, liked_recipe_ids, disliked_recipe_ids
    )
    final = (
        0.40 * pantry_score
        + 0.35 * macro_score
        + 0.15 * cook_score
        + 0.10 * pref_score
    )
    return RecipeScore(
        recipe_id=recipe.recipe_id,
        pantry_match_score=round(clamp(pantry_score), 4),
        pantry_mass_coverage=round(clamp(mass_coverage), 4),
        macro_fit_score=round(clamp(macro_score), 4),
        time_score=round(clamp(cook_score), 4),
        preference_score=round(clamp(pref_score), 4),
        final_score=round(clamp(final), 4),
        missing_ingredients=missing,
        used_ingredients=used,
    )
