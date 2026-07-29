from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.db import SessionLocal
from app.data.models import ChatThread


class ChatThreadRepository:
    """Persistence for `app.data.models.ChatThread` -- mirrors `app.data.
    graph_run_repository.GraphRunRepository`'s constructor/session-lifecycle
    pattern exactly (optional injected `Session` for tests, otherwise a fresh
    `SessionLocal()` per call, closed only when this repository owns it).

    This is the ONLY place `app.api.routes_chat` checks thread ownership --
    the LangGraph checkpointer used by `app.agent.chef_agent` has no concept
    of an owning user, same reasoning as `GraphRun`'s docstring.
    """

    def __init__(self, db: Session | None = None):
        self._external_db = db

    def _session(self) -> Session:
        return self._external_db or SessionLocal()

    def create(self, thread_id: str, owner_user_id: str, user_profile_json: str) -> ChatThread:
        db = self._session()
        close = self._external_db is None
        try:
            row = ChatThread(
                id=thread_id, owner_user_id=owner_user_id, user_profile=user_profile_json
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            if close:
                db.close()

    def get_owned(self, thread_id: str, owner_user_id: str) -> ChatThread | None:
        """Returns the row only if it exists, is active, AND belongs to
        `owner_user_id` -- callers must 404 identically for "no such
        thread_id" and "thread_id exists, wrong owner" (mirrors
        `GraphRunRepository.get_owned`'s identical "no oracle" collapse)."""
        db = self._session()
        close = self._external_db is None
        try:
            return db.scalar(
                select(ChatThread).where(
                    ChatThread.id == thread_id,
                    ChatThread.owner_user_id == owner_user_id,
                    ChatThread.is_active.is_(True),
                )
            )
        finally:
            if close:
                db.close()

    def set_title_if_unset(self, thread_id: str, title: str) -> None:
        """Sets a display-only title (derived from the first user message --
        see `app.agent.chef_agent.run_chef_turn`) ONLY when the thread has
        none yet. Never overwrites an existing title. A no-op (not an error)
        if `thread_id` doesn't exist -- callers already own the row by the
        time they call this."""
        db = self._session()
        close = self._external_db is None
        try:
            row = db.scalar(select(ChatThread).where(ChatThread.id == thread_id))
            if row is None or row.title:
                return
            row.title = title[:256]
            db.commit()
        finally:
            if close:
                db.close()
