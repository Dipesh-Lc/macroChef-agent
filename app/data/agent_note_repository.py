from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.db import SessionLocal
from app.data.models import AgentNote


class AgentNoteRepository:
    """Persistence for `app.data.models.AgentNote` -- the Chef agent's
    long-term per-user memory (ROADMAP.md Phase 3, Step 3.3).

    Advisor-reviewed decisions (Q2), implemented exactly here:
    - `remember()` is the ONLY write path an LLM tool call ever reaches
      (`app.agent.tools.remember`) -- there is deliberately no LLM-facing
      edit or delete method on this class. `soft_delete()` exists ONLY for
      the human-only `DELETE /chat/notes/{id}` REST endpoint
      (`app.api.routes_chat`), which is session-gated and ownership-checked
      there, never reachable from the agent loop.
    - Hard cap of `MAX_ACTIVE_NOTES` (30) active notes per user. `remember()`
      NEVER refuses a new note over the cap -- the user just explicitly
      asked to remember something -- it soft-deletes the single oldest
      active note first instead, then inserts the new one.
    - `NOTE_CHAR_CAP` (280) is enforced here, in code, not just left to the
      DB's `Text` column (which would silently accept anything) -- a note
      longer than this is truncated (never rejected, same "never refuse a
      remember() call" principle as the count cap).

    Mirrors `app.data.graph_run_repository.GraphRunRepository`'s
    constructor/session-lifecycle pattern (optional injected `Session` for
    tests, otherwise a fresh `SessionLocal()` per call).
    """

    MAX_ACTIVE_NOTES = 30
    NOTE_CHAR_CAP = 280

    def __init__(self, db: Session | None = None):
        self._external_db = db

    def _session(self) -> Session:
        return self._external_db or SessionLocal()

    def remember(self, user_id: str, note: str) -> AgentNote:
        text = note.strip()[: self.NOTE_CHAR_CAP]
        db = self._session()
        close = self._external_db is None
        try:
            active = (
                db.scalars(
                    select(AgentNote)
                    .where(AgentNote.user_id == user_id, AgentNote.is_active.is_(True))
                    .order_by(AgentNote.created_at.asc(), AgentNote.id.asc())
                )
                .all()
            )
            if len(active) >= self.MAX_ACTIVE_NOTES:
                oldest = active[0]
                oldest.is_active = False

            row = AgentNote(user_id=user_id, note=text, is_active=True)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            if close:
                db.close()

    def list_active(self, user_id: str) -> list[AgentNote]:
        db = self._session()
        close = self._external_db is None
        try:
            return list(
                db.scalars(
                    select(AgentNote)
                    .where(AgentNote.user_id == user_id, AgentNote.is_active.is_(True))
                    .order_by(AgentNote.created_at.asc(), AgentNote.id.asc())
                ).all()
            )
        finally:
            if close:
                db.close()

    def soft_delete(self, note_id: int, user_id: str) -> bool:
        """Human-only deletion path (`DELETE /chat/notes/{id}`) -- ownership
        checked here (both `id` AND `user_id` in the WHERE clause) so a
        caller can never soft-delete another user's note by guessing its
        integer id. Returns False for "no such note" and "note exists but
        isn't yours" alike -- the route layer 404s on either."""
        db = self._session()
        close = self._external_db is None
        try:
            row = db.scalar(
                select(AgentNote).where(
                    AgentNote.id == note_id,
                    AgentNote.user_id == user_id,
                    AgentNote.is_active.is_(True),
                )
            )
            if row is None:
                return False
            row.is_active = False
            db.commit()
            return True
        finally:
            if close:
                db.close()
