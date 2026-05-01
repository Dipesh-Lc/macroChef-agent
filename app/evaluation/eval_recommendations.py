from app.evaluation.metrics import (
    allergy_violation_rate,
    macro_deviation,
    missing_ingredient_count,
    pantry_utilization_rate,
    recommendation_validity_rate,
)
from app.schemas.recommendation import RecommendationResponse
from app.schemas.user import UserProfile


def summarize_response(response: RecommendationResponse, user_profile: UserProfile) -> dict[str, float]:
    recommendations = response.recommendations
    return {
        "allergy_violation_rate": allergy_violation_rate(recommendations, user_profile),
        "pantry_utilization_rate": pantry_utilization_rate(recommendations),
        "macro_deviation": macro_deviation(recommendations),
        "missing_ingredient_count": missing_ingredient_count(recommendations),
        "recommendation_validity_rate": recommendation_validity_rate(recommendations, user_profile),
    }
