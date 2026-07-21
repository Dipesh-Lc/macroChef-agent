from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.db import SessionLocal
from app.data.models import SharedPlan


class ShareRepository:
    """Persistence for `app.data.models.SharedPlan` -- mirrors
    `app.data.recipe_library_repository.RecipeLibraryRepository`'s
    constructor/session-lifecycle pattern (optional injected `Session` for
    tests, otherwise a fresh `SessionLocal()` per call, closed when this
    repository owns it).

    Deliberately thin: every method here does a plain CRUD op against
    `SharedPlan`. The safety-relevant work (building the allowlisted
    `content` payload) happens one layer up, in
    `app.services.share_service` -- this repository never sees, and never
    needs to see, a raw client-supplied `Recipe`/`DayPlan`/`BatchPlan`/
    `WeeklyPlan`.
    """

    def __init__(self, db: Session | None = None):
        self._external_db = db

    def _session(self) -> Session:
        return self._external_db or SessionLocal()

    def create(
        self, share_id: str, plan_type: str, content_json: str, owner_user_id: str
    ) -> SharedPlan:
        db = self._session()
        close = self._external_db is None
        try:
            row = SharedPlan(
                id=share_id,
                plan_type=plan_type,
                content=content_json,
                owner_user_id=owner_user_id,
                is_active=True,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            if close:
                db.close()

    def get_active(self, share_id: str) -> SharedPlan | None:
        """Returns the row only if it exists AND `is_active` -- callers
        (app.api.routes_share.get_share_view) must 404 identically for
        "never existed" and "revoked", so this method deliberately does not
        distinguish the two: both return None here."""
        db = self._session()
        close = self._external_db is None
        try:
            return db.scalar(
                select(SharedPlan).where(
                    SharedPlan.id == share_id,
                    SharedPlan.is_active.is_(True),
                )
            )
        finally:
            if close:
                db.close()

    def exists(self, share_id: str) -> bool:
        """Test/debug helper only (e.g. proving a row was persisted with a
        real owner_user_id) -- never used on the anonymous GET path."""
        db = self._session()
        close = self._external_db is None
        try:
            return (
                db.scalar(select(SharedPlan).where(SharedPlan.id == share_id)) is not None
            )
        finally:
            if close:
                db.close()
