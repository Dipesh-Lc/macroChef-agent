from fastapi import APIRouter, Depends

from app.config import get_settings
from app.dependencies import require_recommend_rate_limit
from app.graph.builder import run_recommendation_graph
from app.schemas.instructions import DetailedInstructionsRequest, DetailedInstructionsResponse
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.model_provider import generate_detailed_instructions_with_provider_chain

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


@router.post("/instructions", response_model=DetailedInstructionsResponse)
def get_detailed_instructions(
    request: DetailedInstructionsRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> DetailedInstructionsResponse:
    # Session-gated and rate-limited the exact same way as POST
    # /recipes/recommend (require_recommend_rate_limit resolves
    # app.dependencies.get_session_user internally before keying the rate
    # limit) -- this reuses that endpoint's existing, already-tested
    # session/rate-limit tier rather than inventing a new one. `session_user_id`
    # is otherwise unused here: this endpoint is a pure function of its
    # request body (it reads/writes no per-user data), so the only reason it
    # requires a session at all is to share the same abuse-guard bucket as
    # the other LLM-backed /recipes/* call.
    del session_user_id
    settings = get_settings()
    steps, generated = generate_detailed_instructions_with_provider_chain(
        title=request.title,
        ingredients=request.ingredients,
        instructions=request.instructions,
        servings=request.servings,
        cuisine=request.cuisine,
    )
    provider_note = None
    if not generated:
        if settings.model_provider == "mock":
            provider_note = "Detailed generation is unavailable in mock mode; showing the original steps."
        else:
            provider_note = (
                "Detailed generation is temporarily unavailable; showing the original steps."
            )
    return DetailedInstructionsResponse(steps=steps, generated=generated, provider_note=provider_note)
