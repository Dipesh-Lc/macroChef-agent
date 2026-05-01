from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import RecipeScore
from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.procurement_service import split_used_and_missing


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def pantry_match_score(recipe: Recipe, inventory: list[ConfirmedIngredient]) -> tuple[float, list[str], list[str]]:
    used, missing = split_used_and_missing(recipe, inventory)
    if not recipe.ingredients:
        return 0.0, used, missing
    return len(used) / len(recipe.ingredients), used, missing


def _macro_value(recipe: Recipe, name: str) -> float | None:
    return getattr(recipe, name)


def macro_fit_score(recipe: Recipe, targets: MacroTargets) -> float:
    fields = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g"]
    errors: list[float] = []
    for field in fields:
        target = getattr(targets, field)
        actual = _macro_value(recipe, field)
        if target is None or target <= 0 or actual is None:
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
    pantry_score, used, missing = pantry_match_score(recipe, inventory)
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
        macro_fit_score=round(clamp(macro_score), 4),
        time_score=round(clamp(cook_score), 4),
        preference_score=round(clamp(pref_score), 4),
        final_score=round(clamp(final), 4),
        missing_ingredients=missing,
        used_ingredients=used,
    )
