"""Structured run events for the recommend/library LangGraph pipelines.

Why this exists (ROADMAP.md Phase 1, Step 1.1): every serious AI team runs
on traces. This module is deliberately small and dependency-free (no OTel,
no external backend -- that's Step 1.3) so it's cheap to build and safe to
apply to all 19 graph nodes today. It is prerequisite plumbing: the LLM
cost ledger (1.2) and SSE streaming (3.1) both consume this same event
shape.

Design notes for future readers:
- `RunEvent` never carries a full domain object (a `Recipe`, a `UserProfile`,
  ...) in `payload` -- only small counts/flags. This is a *safety* property
  as much as a size one: this stream is the natural place a future SSE
  endpoint (3.1) or admin page would surface verbatim, and it must never
  become a second channel that leaks allergy/PII-shaped data alongside the
  vetted API response schemas.
- `InMemorySink` is written for the not-yet-built SSE endpoint (3.1): a
  consumer must be able to call `get_events(run_id)` repeatedly *while the
  run is still in progress* and get whatever has landed so far, not just
  after completion. That's why it's a plain per-run list behind a lock
  rather than, say, a one-shot future.
- Nothing here decides an allergy/diet outcome or computes nutrition --
  it only observes and reports on nodes that already did (see
  app.services.constraint_engine). Never let a payload/summary become a
  second source of truth a caller could act on instead of the real
  response schema.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from functools import wraps
from threading import Lock
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# run_id / request-id contextvar
#
# One id flows through both HTTP logs (app.utils.logging) and every
# RunEvent for a given request -- set once by the request-id middleware
# (app.main.RequestIdMiddleware) and read here by whichever node/log call
# happens to run inside that request's async context. Falls back to a
# freshly minted id when nothing set one (e.g. a script or test calling a
# graph node directly, outside any HTTP request) so callers never have to
# special-case "no request in flight".
# ---------------------------------------------------------------------------

_RUN_ID_CTX: ContextVar[str | None] = ContextVar("macrochef_run_id", default=None)


def new_run_id() -> str:
    """Mint a fresh opaque run/request id. Not a secret; purely a
    correlation key for logs/traces."""
    return uuid.uuid4().hex


def get_run_id() -> str:
    """Return the current run id, minting and storing a fresh one if none
    is set yet in this context (see module docstring)."""
    run_id = _RUN_ID_CTX.get()
    if run_id is None:
        run_id = new_run_id()
        _RUN_ID_CTX.set(run_id)
    return run_id


def peek_run_id() -> str | None:
    """Like `get_run_id`, but never mints one -- returns None if unset.
    Used by the logging filter, which must not itself mint ids for log
    lines emitted outside any request/run context."""
    return _RUN_ID_CTX.get()


def set_run_id(run_id: str) -> Token:
    """Bind `run_id` in the current context; returns a Token for
    `reset_run_id` (mirrors `contextvars.ContextVar.set`/`.reset`)."""
    return _RUN_ID_CTX.set(run_id)


def reset_run_id(token: Token) -> None:
    _RUN_ID_CTX.reset(token)


# ---------------------------------------------------------------------------
# user_id contextvar (ROADMAP 1.2)
#
# `user_id` is the LLM call ledger's other correlation key (alongside
# run_id above), but unlike run_id it is NOT threaded through every graph
# node's signature -- model_provider.py's `_generate_text`/`_extract_
# inventory` choke points are several call-frames below the handful of
# entry points that actually resolve a verified user_id
# (app.graph.builder.run_recommendation_graph,
# app.graph.library_builder.run_library_discovery_graph/
# run_library_save_graph, app.api.routes_recommendations.
# get_detailed_instructions). Those entry points bind it here, once, the
# same way app.main.RequestIdMiddleware binds run_id per request; anything
# deeper in the call stack (app.observability.llm_ledger.record_llm_call)
# reads it back via `peek_user_id()`.
#
# Deliberately no `get_user_id()` mint-on-miss sibling the way `get_run_id`
# has for run_id: there is no sensible synthetic user id to invent, and
# some call paths are genuinely anonymous/unauthenticated (e.g. POST
# /inventory/extract, which requires no session at all) -- the ledger must
# persist a NULL user_id there, not a fabricated one.
#
# NEVER put this in a RunEvent's `payload`/`summary` -- see this module's
# docstring on why that stream must stay free of anything PII-shaped. It
# is only ever written to the `llm_calls` SQL table (a private,
# session-gated-but-not-per-user-scoped admin view; see
# app.api.routes_admin).
# ---------------------------------------------------------------------------

_USER_ID_CTX: ContextVar[str | None] = ContextVar("macrochef_user_id", default=None)


def bind_user_id(user_id: str | None) -> Token:
    """Bind the verified session user id for the current context. Returns a
    Token for `reset_user_id` (mirrors `set_run_id`/`reset_run_id`).
    Passing `None` is valid and means "no verified user in this context" --
    never guessed at, never defaulted to a placeholder string."""
    return _USER_ID_CTX.set(user_id)


def peek_user_id() -> str | None:
    """Return the currently bound user id, or None if nothing was bound in
    this context. Never mints a value -- see module note above."""
    return _USER_ID_CTX.get()


def reset_user_id(token: Token) -> None:
    _USER_ID_CTX.reset(token)


# ---------------------------------------------------------------------------
# RunEvent + sinks
# ---------------------------------------------------------------------------


class RunEvent(BaseModel):
    """One lifecycle event for one graph node execution.

    `summary` is always one human sentence (the same convention the
    existing `debug_trace` entries already use, e.g. "Retrieved 14
    candidates from 5,200-recipe corpus") -- never structured data; that
    belongs in `payload`, and `payload` itself stays small (counts/flags),
    never a full domain object (see module docstring).
    """

    run_id: str
    node: str
    status: Literal["started", "finished", "failed"]
    elapsed_ms: float | None = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class EventSink(Protocol):
    def emit(self, event: RunEvent) -> None: ...


class InMemorySink:
    """Per-run, in-process event buffer.

    Built for the Phase 3 SSE endpoint: a consumer calls `get_events(run_id)`
    at any time -- including while the run is still executing -- and gets
    everything emitted so far. Thread-safe (nodes may run off the asyncio
    loop via FastAPI's threadpool, see app.main.RequestIdMiddleware's
    docstring on why contextvars still reach them). Unbounded per run_id;
    callers own lifecycle cleanup via `clear()` once a run's events have
    been fully relayed (not wired up yet -- that's Step 3.1's job).
    """

    def __init__(self) -> None:
        self._events: dict[str, list[RunEvent]] = defaultdict(list)
        self._lock = Lock()

    def emit(self, event: RunEvent) -> None:
        with self._lock:
            self._events[event.run_id].append(event)

    def get_events(self, run_id: str) -> list[RunEvent]:
        """Snapshot of everything emitted for `run_id` so far. Safe to call
        mid-run -- returns a copy, never the live list."""
        with self._lock:
            return list(self._events.get(run_id, []))

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._events.pop(run_id, None)


class LogSink:
    """Emits one structured JSON log line per event.

    The default sink today (Step 1.3 will add an OTel span exporter
    alongside/instead of this). Uses the stdlib `logging` module directly
    (not `app.utils.logging.get_logger`) to avoid a two-way import between
    this module and `app.utils.logging` (which itself reads `peek_run_id`
    from here to stamp ordinary log lines with the request id).
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("app.observability.events")

    def emit(self, event: RunEvent) -> None:
        self._logger.info(json.dumps(event.model_dump(mode="json")))


_default_sink: EventSink = LogSink()


def get_default_sink() -> EventSink:
    return _default_sink


def set_default_sink(sink: EventSink) -> None:
    """Swap the process-wide default sink `traced_node` falls back to when
    no explicit `sink=` is passed. Primarily for tests (point it at an
    `InMemorySink` to assert on emitted events) and, later, for wiring the
    SSE endpoint's per-run sink."""
    global _default_sink
    _default_sink = sink


# ---------------------------------------------------------------------------
# traced_node decorator
# ---------------------------------------------------------------------------


def _debug_trace_of(state: Any) -> list[str]:
    """Read `debug_trace` off either a Pydantic state model or the plain
    dict a node returns -- both `MacroChefState` and
    `RecipeLibraryBuilderState` carry this field under the same name."""
    if isinstance(state, BaseModel):
        return list(getattr(state, "debug_trace", None) or [])
    if isinstance(state, dict):
        return list(state.get("debug_trace") or [])
    return []


def traced_node(
    name: str,
    sink: EventSink | None = None,
    payload_fn: Callable[[Any, Any], dict[str, Any]] | None = None,
):
    """Wrap a graph node function with started/finished/failed `RunEvent`s.

    - Emits `started` before calling the node, `finished` after a
      successful return (with `elapsed_ms`), or `failed` (with
      `elapsed_ms`) if the node raises -- the original exception is always
      re-raised unchanged (callers must see the real exception, never one
      wrapped by this decorator).
    - The event's human `summary` is the node's own new `debug_trace`
      entry/entries (nodes already write exactly one clear sentence about
      what they did -- see app.graph.nodes._trace /
      app.graph.library_nodes._trace) when the node adds one. Some nodes
      short-circuit without adding one (e.g. "upstream errors already
      exist, no-op") -- in that case this decorator both synthesizes a
      generic summary AND appends it to `debug_trace` itself, so every
      *executed* node still leaves exactly one trace line, keeping the
      existing wire format's guarantee intact rather than silently
      degrading it just because a node happened to short-circuit. When the
      node already added its own entry, `debug_trace` is left exactly as
      the node produced it -- no duplicate line.
    - `sink` defaults to the process-wide `get_default_sink()` at CALL time
      (not decoration time), so tests/scripts can swap sinks via
      `set_default_sink` without needing to re-decorate anything.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            active_sink = sink if sink is not None else get_default_sink()
            run_id = get_run_id()
            input_state = args[0] if args else kwargs.get("state")
            before_trace = _debug_trace_of(input_state)

            active_sink.emit(
                RunEvent(
                    run_id=run_id,
                    node=name,
                    status="started",
                    summary=f"{name}: started.",
                )
            )
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                active_sink.emit(
                    RunEvent(
                        run_id=run_id,
                        node=name,
                        status="failed",
                        elapsed_ms=elapsed_ms,
                        summary=f"{name}: failed after {elapsed_ms:.1f}ms ({exc}).",
                        payload={"error_type": type(exc).__name__},
                    )
                )
                raise

            elapsed_ms = (time.perf_counter() - start) * 1000
            after_trace = _debug_trace_of(result)
            new_entries = after_trace[len(before_trace) :]

            if new_entries:
                summary = " ".join(new_entries)
            else:
                summary = f"{name}: completed in {elapsed_ms:.1f}ms (no state change)."
                if isinstance(result, dict):
                    result = {**result, "debug_trace": [*before_trace, summary]}
                # A node's contract (ensure_state/library_state_update) is to
                # always return a plain dict -- see app.graph.state.
                # state_update / app.graph.library_state.
                # library_state_update, both called by every node in
                # app/graph/nodes.py and app/graph/library_nodes.py. If a
                # future node ever breaks that contract, fall through here
                # without touching debug_trace rather than guessing at a
                # BaseModel's field layout.

            payload = payload_fn(input_state, result) if payload_fn else {}
            active_sink.emit(
                RunEvent(
                    run_id=run_id,
                    node=name,
                    status="finished",
                    elapsed_ms=elapsed_ms,
                    summary=summary,
                    payload=payload,
                )
            )
            return result

        return wrapper

    return decorator
