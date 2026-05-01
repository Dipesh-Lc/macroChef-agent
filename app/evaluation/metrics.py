from app.schemas.recommendation import MealRecommendation
from app.schemas.user import UserProfile
from app.services.constraint_engine import validate_recipe


def allergy_violation_rate(
    recommendations: list[MealRecommendation], user_profile: UserProfile
) -> float:
    if not recommendations:
        return 0.0
    violations = sum(
        1 for recommendation in recommendations if not validate_recipe(recommendation.recipe, user_profile).is_valid
    )
    return violations / len(recommendations)


def pantry_utilization_rate(recommendations: list[MealRecommendation]) -> float:
    if not recommendations:
        return 0.0
    return sum(item.score.pantry_match_score for item in recommendations) / len(recommendations)


def macro_deviation(recommendations: list[MealRecommendation]) -> float:
    if not recommendations:
        return 0.0
    return sum(1.0 - item.score.macro_fit_score for item in recommendations) / len(recommendations)


def missing_ingredient_count(recommendations: list[MealRecommendation]) -> float:
    if not recommendations:
        return 0.0
    return sum(len(item.score.missing_ingredients) for item in recommendations) / len(recommendations)


def recommendation_validity_rate(
    recommendations: list[MealRecommendation], user_profile: UserProfile
) -> float:
    if not recommendations:
        return 0.0
    valid = sum(1 for item in recommendations if validate_recipe(item.recipe, user_profile).is_valid)
    return valid / len(recommendations)
