from fastapi import APIRouter, Depends

from app.dependencies import require_recommend_rate_limit
from app.graph.builder import run_recommendation_graph
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse

router = APIRouter(prefix="/recipes", tags=["recommendations"])


@router.post("/recommend", response_model=RecommendationResponse)
def recommend_recipes(
    request: RecommendationRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> RecommendationResponse:
    # `session_user_id` is the verified session identity (see
    # app.dependencies.get_session_user, which require_recommend_rate_limit
    # resolves internally before keying the rate limit on it). It is now also
    # the ONLY identity used for this request -- there is no client-supplied
    # `user_id` on `RecommendationRequest` to fall back to or be confused
    # with. This is what list_user_recipes/get_user_memory/
    # save_session_summary key personalization and saved-library reads on
    # inside the recommendation graph (see app.graph.builder).
    return run_recommendation_graph(request, session_user_id)
