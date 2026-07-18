from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db_session, get_session_user
from app.schemas.recommendation import FeedbackRequest
from app.services.memory_service import save_feedback

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def post_feedback(
    request: FeedbackRequest,
    user_id: str = Depends(get_session_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    # `user_id` is the verified session identity (see
    # app.dependencies.get_session_user) -- it is now the ONLY identity used
    # for this request. There is no client-supplied `user_id` on
    # `FeedbackRequest` to fall back to or be confused with (this was the
    # third instance of the same bug class closed for /library in commit
    # 58053d3 and for /recipes/recommend shortly before this fix).
    return save_feedback(user_id, request, db)
