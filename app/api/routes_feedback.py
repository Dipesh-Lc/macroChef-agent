from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db_session
from app.schemas.recommendation import FeedbackRequest
from app.services.memory_service import save_feedback

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def post_feedback(request: FeedbackRequest, db: Session = Depends(get_db_session)) -> dict[str, str]:
    return save_feedback(request, db)
