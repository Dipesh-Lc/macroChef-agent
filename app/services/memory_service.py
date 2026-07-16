from sqlalchemy.orm import Session

from app.data.db import SessionLocal, init_db
from app.data.repositories import FeedbackRepository, SessionMemoryRepository
from app.schemas.recommendation import FeedbackRequest, MealRecommendation
from app.services.analytics import get_analytics

# feedback_type values that map onto a thumbs up/down analytics signal.
# "cooked"/"skipped" are other feedback types this endpoint accepts but are
# not thumbs up/down, so they are not captured here.
_THUMBS_EVENT_BY_FEEDBACK_TYPE = {"liked": "thumbs_up", "disliked": "thumbs_down"}


def save_feedback(request: FeedbackRequest, db: Session | None = None) -> dict[str, str]:
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        FeedbackRepository(session).add_feedback(request)
        thumbs_event = _THUMBS_EVENT_BY_FEEDBACK_TYPE.get(request.feedback_type)
        if thumbs_event:
            get_analytics().capture(
                request.user_id,
                "thumbs up/down",
                {"direction": thumbs_event, "recipe_id": request.recipe_id},
            )
        return {"status": "ok", "message": "Feedback saved"}
    finally:
        if owns_session:
            session.close()


def get_user_memory(user_id: str, db: Session | None = None) -> tuple[set[str], set[str]]:
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        repo = FeedbackRepository(session)
        return repo.get_liked_recipe_ids(user_id), repo.get_disliked_recipe_ids(user_id)
    finally:
        if owns_session:
            session.close()


def save_session_summary(
    user_id: str, recommendations: list[MealRecommendation], db: Session | None = None
) -> str:
    if not recommendations:
        return "No recommendations saved."
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    summary = "Recommended: " + ", ".join(item.recipe.title for item in recommendations)
    try:
        SessionMemoryRepository(session).add_summary(user_id=user_id, summary=summary)
        return summary
    finally:
        if owns_session:
            session.close()
