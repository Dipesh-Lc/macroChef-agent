from fastapi import APIRouter

from app.graph.builder import run_recommendation_graph
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse

router = APIRouter(prefix="/recipes", tags=["recommendations"])


@router.post("/recommend", response_model=RecommendationResponse)
def recommend_recipes(request: RecommendationRequest) -> RecommendationResponse:
    return run_recommendation_graph(request)
