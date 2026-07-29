from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.db import SessionLocal
from app.data.models import GraphRun


class GraphRunRepository:
    """Persistence for `app.data.models.GraphRun` -- mirrors
    `app.data.share_repository.ShareRepository`'s constructor/session-
    lifecycle pattern (optional injected `Session` for tests, otherwise a
    fresh `SessionLocal()` per call, closed when this repository owns it).

    This is the ONLY place `app.api.routes_runs` checks thread ownership --
    it never asks the LangGraph checkpointer, which has no concept of an
    owning user (see `GraphRun`'s own docstring).
    """

    def __init__(self, db: Session | None = None):
        self._external_db = db

    def _session(self) -> Session:
        return self._external_db or SessionLocal()

    def create(self, thread_id: str, owner_user_id: str) -> GraphRun:
        db = self._session()
        close = self._external_db is None
        try:
            row = GraphRun(id=thread_id, owner_user_id=owner_user_id)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            if close:
                db.close()

    def get_owned(self, thread_id: str, owner_user_id: str) -> GraphRun | None:
        """Returns the row only if it exists AND belongs to `owner_user_id`
        -- callers (`app.api.routes_runs`) must 404 identically for "no
        such thread_id" and "thread_id exists, wrong owner", so this
        method deliberately does not distinguish the two: both return
        None here (mirrors `ShareRepository.get_active`'s identical
        "no oracle" collapse)."""
        db = self._session()
        close = self._external_db is None
        try:
            return db.scalar(
                select(GraphRun).where(
                    GraphRun.id == thread_id,
                    GraphRun.owner_user_id == owner_user_id,
                )
            )
        finally:
            if close:
                db.close()
