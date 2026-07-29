"""Thread transcript persistence + reconstruction for the Chef agent
(ROADMAP.md Phase 3, Step 3.3).

`TranscriptEntry`/`ToolCallLogEntry` are the small Pydantic records
`app.agent.chef_agent`'s `ChefState` threads through the ReAct loop --
defined HERE (not in `chef_agent.py`) so this module never needs to import
the graph-wiring module back; `chef_agent.py` imports these FROM here.

Long-term, cross-thread memory (the `agent_notes` table / `remember()` tool)
lives in `app.data.agent_note_repository.AgentNoteRepository`, used directly
by `app.agent.tools`'s `get_user_context`/`remember` handlers -- kept there
rather than re-exported here so every tool handler follows the same "thin
wrapper directly over its backing repository/service" shape (see
`app.agent.tools`'s module docstring).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.data.db import SessionLocal
from app.data.models import ChatMessage


class TranscriptEntry(BaseModel):
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool: str | None = None


class ToolCallLogEntry(BaseModel):
    """One tool call's outcome for THIS turn -- mirrors `app.agent.tools.
    ToolResult` field-for-field (plus `args`, the call's own input), and is
    what `app.agent.chef_agent.evaluate_response_gate` scans for coverage.
    Persisted verbatim (via `persist_turn`) into `ChatMessage.tool_calls_json`."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    summary: str
    raw: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    recipe_ids_covered: list[str] = Field(default_factory=list)


def load_transcript(thread_id: str) -> list[TranscriptEntry]:
    """Reconstruct the conversation this thread's NEXT turn should see: only
    `user`/`assistant` rows, oldest first. Historical `tool` rows are
    deliberately NOT replayed back into a future turn's prompt -- they are
    per-turn scratch space the agent already summarized into its own
    `assistant` answer; re-feeding every past `<tool_output>` verbatim would
    balloon prompt size for no benefit past the turn that produced it. (The
    full tool-call history, including `tool` rows, is still durably stored
    by `persist_turn` for `GET /chat/{thread_id}`'s audit display.)
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == thread_id,
                ChatMessage.role.in_(["user", "assistant"]),
            )
            .order_by(ChatMessage.id.asc())
            .all()
        )
        return [TranscriptEntry(role=row.role, content=row.content) for row in rows]
    finally:
        db.close()


def persist_turn(
    thread_id: str,
    user_message: str,
    assistant_message: str,
    tool_call_log: list[ToolCallLogEntry],
) -> None:
    """Durably records one full turn -- the user's message, one row per tool
    call executed (audit trail for the chat UI's tool-call chips, ROADMAP
    Phase 4.3), then the assistant's final answer -- in that order, so
    `GET /chat/{thread_id}` can replay the turn faithfully."""
    db = SessionLocal()
    try:
        db.add(ChatMessage(thread_id=thread_id, role="user", content=user_message))
        for entry in tool_call_log:
            db.add(
                ChatMessage(
                    thread_id=thread_id,
                    role="tool",
                    content=entry.summary,
                    tool_calls_json=json.dumps(entry.model_dump()),
                )
            )
        db.add(
            ChatMessage(
                thread_id=thread_id,
                role="assistant",
                content=assistant_message,
                tool_calls_json=json.dumps([entry.model_dump() for entry in tool_call_log]),
            )
        )
        db.commit()
    finally:
        db.close()
