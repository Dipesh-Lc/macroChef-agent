from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models import Feedback, SessionMemory
from app.schemas.recommendation import FeedbackRequest


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_feedback(self, request: FeedbackRequest) -> Feedback:
        feedback = Feedback(
            user_id=request.user_id,
            recipe_id=request.recipe_id,
            feedback_type=request.feedback_type,
            notes=request.notes,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def get_feedback_for_user(self, user_id: str) -> list[Feedback]:
        stmt = select(Feedback).where(Feedback.user_id == user_id)
        return list(self.db.scalars(stmt).all())

    def get_liked_recipe_ids(self, user_id: str) -> set[str]:
        stmt = select(Feedback.recipe_id).where(
            Feedback.user_id == user_id,
            Feedback.feedback_type.in_(["liked", "cooked"]),
        )
        return set(self.db.scalars(stmt).all())

    def get_disliked_recipe_ids(self, user_id: str) -> set[str]:
        stmt = select(Feedback.recipe_id).where(
            Feedback.user_id == user_id,
            Feedback.feedback_type.in_(["disliked", "skipped"]),
        )
        return set(self.db.scalars(stmt).all())


class SessionMemoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_summary(self, user_id: str, summary: str) -> SessionMemory:
        item = SessionMemory(user_id=user_id, summary=summary)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
