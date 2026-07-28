"""Structured run events + request-id tracing (ROADMAP 1.1).

Prerequisite plumbing for later phases: the LLM cost ledger (1.2), OTel
spans (1.3), and SSE streaming (3.1) all consume the same `RunEvent`
stream defined here. See `app.observability.events` for the actual
implementation; this package re-exports the small public surface other
modules need.
"""

from app.observability.events import (
    EventSink,
    InMemorySink,
    LogSink,
    RunEvent,
    bind_user_id,
    get_default_sink,
    get_run_id,
    new_run_id,
    peek_user_id,
    reset_run_id,
    reset_user_id,
    set_default_sink,
    set_run_id,
    traced_node,
)

__all__ = [
    "EventSink",
    "InMemorySink",
    "LogSink",
    "RunEvent",
    "bind_user_id",
    "get_default_sink",
    "get_run_id",
    "new_run_id",
    "peek_user_id",
    "reset_run_id",
    "reset_user_id",
    "set_default_sink",
    "set_run_id",
    "traced_node",
]
