from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.user import UserProfile

# ROADMAP.md Phase 3, Step 3.3: wire schemas for the "Chef" conversational
# agent (app.api.routes_chat). Additive -- does not touch any existing
# schema module.


class ChatCreateRequest(BaseModel):
    # Bound ONCE, here, at thread-creation time -- see `app.data.models.
    # ChatThread.user_profile`'s docstring for why this can never become a
    # per-message/tool-call argument afterward.
    user_profile: UserProfile


class ChatCreateResponse(BaseModel):
    thread_id: str


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageView(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    created_at: datetime


class ChatThreadStatusResponse(BaseModel):
    thread_id: str
    title: str | None = None
    messages: list[ChatMessageView] = Field(default_factory=list)
