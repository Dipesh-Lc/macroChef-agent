""""Chef" conversational agent HTTP surface (ROADMAP.md Phase 3, Step 3.3).

- `POST /chat` -- creates a thread, binds `user_profile` ONCE (client-
  supplied in this call only -- see `app.data.models.ChatThread`'s
  docstring for why it can never become a per-message/tool-call argument
  afterward).
- `POST /chat/{thread_id}/message` -- SSE turn endpoint. Mirrors `app.api.
  routes_stream`'s worker-thread + in-memory-sink-polling architecture
  (NOT native `graph.stream()`/`astream()`) for the same reason that module
  gives: it must keep working whether or not `langgraph` is importable, and
  it needs exactly one node/tool -> event translation path, not two.
- `GET /chat/{thread_id}` -- thread status/history, 404 on cross-user
  access (mirrors `app.api.routes_runs`' identical `GraphRun` "no oracle"
  collapse -- advisor-reviewed decision, Q3/Q5).
- `DELETE /chat/notes/{note_id}` -- human-only note deletion. The Chef
  agent's `remember()` tool can only ever APPEND a note (see `app.agent.
  tools.RememberArgs`) -- this is the only path that can ever remove one,
  session-gated and ownership-checked here, never reachable from the agent
  loop.

Every route is session-gated via `app.dependencies.get_session_user` (or
the chat-specific rate-limited wrapper, `require_chat_message_rate_limit`)
-- `user_id` always comes from the verified session token, never a request
body (CLAUDE.md invariant #3).
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.chef_agent import (
    ChatEventSink,
    bind_chat_event_sink,
    reset_chat_event_sink,
    run_chef_turn,
)
from app.data.agent_note_repository import AgentNoteRepository
from app.data.chat_thread_repository import ChatThreadRepository
from app.data.db import SessionLocal
from app.data.models import ChatMessage
from app.dependencies import get_session_user, require_chat_message_rate_limit
from app.schemas.chat import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatMessageRequest,
    ChatMessageView,
    ChatThreadStatusResponse,
)
from app.schemas.user import UserProfile

router = APIRouter(prefix="/chat", tags=["chat"])

# Opaque thread id length -- 128 bits, matching the house pattern used for
# every other opaque public id in this codebase (app.api.routes_runs'
# _THREAD_ID_BYTES, app.services.share_service's _SHARE_ID_BYTES).
_THREAD_ID_BYTES = 16

# Same polling/heartbeat cadence as app.api.routes_stream -- see that
# module's constants for the full rationale (ACA ingress idle-close, "live
# enough for a demo without spinning the loop needlessly").
POLL_INTERVAL_SECONDS = 0.05
HEARTBEAT_INTERVAL_SECONDS = 10.0


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("", response_model=ChatCreateResponse)
def create_chat_thread(
    request: ChatCreateRequest, session_user_id: str = Depends(get_session_user)
) -> ChatCreateResponse:
    thread_id = secrets.token_urlsafe(_THREAD_ID_BYTES)
    ChatThreadRepository().create(
        thread_id, session_user_id, request.user_profile.model_dump_json()
    )
    return ChatCreateResponse(thread_id=thread_id)


def _normalize_tool_calls(tool_calls_json: str | None) -> list[dict[str, Any]] | None:
    """`ChatMessage.tool_calls_json` holds a single dict for a `tool`-role
    row (one call's own entry) and a list for an `assistant`-role row (the
    whole turn's history) -- see `app.agent.memory.persist_turn`. Normalized
    to always be a list here so `ChatMessageView.tool_calls` has one shape
    regardless of role."""
    if not tool_calls_json:
        return None
    parsed = json.loads(tool_calls_json)
    return parsed if isinstance(parsed, list) else [parsed]


@router.get("/{thread_id}", response_model=ChatThreadStatusResponse)
def get_chat_thread(
    thread_id: str, session_user_id: str = Depends(get_session_user)
) -> ChatThreadStatusResponse:
    """404s identically for "no such thread_id" and "thread_id exists,
    belongs to someone else" -- see `app.data.chat_thread_repository.
    ChatThreadRepository.get_owned`'s docstring."""
    thread = ChatThreadRepository().get_owned(thread_id, session_user_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    db = SessionLocal()
    try:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        messages = [
            ChatMessageView(
                role=row.role,
                content=row.content,
                tool_calls=_normalize_tool_calls(row.tool_calls_json),
                created_at=row.created_at,
            )
            for row in rows
        ]
    finally:
        db.close()

    return ChatThreadStatusResponse(thread_id=thread_id, title=thread.title, messages=messages)


async def _stream_chat_turn(
    thread_id: str, user_id: str, user_profile: UserProfile, message: str
) -> AsyncIterator[str]:
    sink = ChatEventSink()
    sink_token = bind_chat_event_sink(sink)
    sent = 0
    last_activity = time.monotonic()

    task = asyncio.ensure_future(
        asyncio.to_thread(run_chef_turn, thread_id, user_id, user_profile, message)
    )

    try:
        while not task.done():
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            events = sink.snapshot()
            if len(events) > sent:
                for event in events[sent:]:
                    yield _sse(event.event, event.data)
                sent = len(events)
                last_activity = time.monotonic()
            elif time.monotonic() - last_activity >= HEARTBEAT_INTERVAL_SECONDS:
                yield ": heartbeat\n\n"
                last_activity = time.monotonic()

        events = sink.snapshot()
        for event in events[sent:]:
            yield _sse(event.event, event.data)
    finally:
        reset_chat_event_sink(sink_token)

    try:
        result = task.result()
    except Exception as exc:
        # Same deliberately-generic shape app.api.routes_stream uses for a
        # mid-graph exception -- never the raw exception message.
        yield _sse("error", {"detail": "Internal Server Error", "error_type": type(exc).__name__})
        return

    # No real token-by-token streaming: `generate_structured` is a single
    # blocking structured call, not a token-streaming API (see
    # app.agent.chef_agent's module docstring). One `token` event carrying
    # the whole final answer keeps the wire vocabulary from spec section 2.5
    # intact without fabricating fake incremental deltas.
    yield _sse("token", {"delta": result.assistant_message})
    yield _sse(
        "message",
        {"role": "assistant", "content": result.assistant_message, "tool_calls": result.tool_calls},
    )


@router.post("/{thread_id}/message")
async def post_chat_message(
    thread_id: str,
    request: ChatMessageRequest,
    session_user_id: str = Depends(require_chat_message_rate_limit),
) -> StreamingResponse:
    """SSE turn endpoint: `token` (final content), `tool_call`/`tool_result`
    (live, as each tool executes), terminal `message`, or `error`."""
    thread = ChatThreadRepository().get_owned(thread_id, session_user_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    user_profile = UserProfile.model_validate_json(thread.user_profile)
    ChatThreadRepository().set_title_if_unset(thread_id, request.message)

    return StreamingResponse(
        _stream_chat_turn(thread_id, session_user_id, user_profile, request.message),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.delete("/notes/{note_id}")
def delete_agent_note(
    note_id: int, session_user_id: str = Depends(get_session_user)
) -> dict[str, str]:
    """Human-only deletion path -- session-gated, ownership-checked
    (`AgentNoteRepository.soft_delete` requires both `note_id` AND
    `user_id` to match). The Chef agent has no delete tool at all; see
    `app.agent.tools`'s module docstring."""
    deleted = AgentNoteRepository().soft_delete(note_id, session_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok"}
