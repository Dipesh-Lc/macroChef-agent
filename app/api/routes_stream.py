"""SSE streaming of recommend-graph progress (ROADMAP.md Phase 3, Step 3.1).

`POST /recipes/recommend/stream` is an ADDITIVE sibling of
`POST /recipes/recommend` (app.api.routes_recommendations) -- same request
body, same session gate, same rate-limit bucket -- that relays each graph
node's `RunEvent`s (app.observability.events) live as Server-Sent Events
while the run is in flight, instead of blocking silently for the 20-45s a
full run can take. It changes NOTHING about the existing synchronous
endpoint or `run_recommendation_graph` itself; this module only observes
what those already emit.

Architecture decision -- worker-thread + `InMemorySink` polling, NOT native
`graph.stream()`/`astream()`:

`build_macrochef_graph()` (app.graph.builder) returns either a real compiled
LangGraph `StateGraph` OR, if `langgraph` itself fails to import,
`SequentialMacroChefGraph` -- and the roadmap step requires this endpoint to
keep working (with per-node events) in the fallback case too. LangGraph's
`.stream()` only yields state deltas AFTER each superstep completes (no
"started" boundary without extra per-node callback plumbing), and has no
equivalent at all on the sequential fallback runner -- driving the SSE feed
off it would mean reinventing the "started" half of every event AND
maintaining two separate node->event translation code paths.

Instead: `run_recommendation_graph` (unmodified) runs inside
`asyncio.to_thread`, and this module polls a per-request `InMemorySink` that
every `@traced_node`-wrapped node (already applied to all 11 recommend-graph
nodes) writes into as it executes -- uniformly, whether the underlying
`.invoke()` is LangGraph's or `SequentialMacroChefGraph`'s, since both share
that call signature. `asyncio.to_thread` copies this coroutine's
`contextvars.Context` (see `app.observability.events.bind_sink_override`)
into the worker thread, so this ONE request's events land in THIS request's
sink, without touching the process-wide default sink any other concurrent
request (including a plain `POST /recipes/recommend`) uses.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import require_recommend_rate_limit
from app.graph.builder import run_recommendation_graph
from app.observability.events import (
    InMemorySink,
    bind_sink_override,
    get_run_id,
    reset_sink_override,
)
from app.schemas.recommendation import RecommendationRequest

router = APIRouter(prefix="/recipes", tags=["recommendations"])

# How often the generator polls the per-run InMemorySink for newly emitted
# node events while the graph runs in its worker thread. Small enough that
# node-boundary events feel live in a demo without spinning the event loop
# needlessly; the graph run itself (20-45s) dwarfs this.
POLL_INTERVAL_SECONDS = 0.05

# Azure Container Apps' ingress idle-closes a connection with no bytes sent
# for a while -- see docs/DEPLOY.md's SSE note. An SSE comment line
# (`: ...\n\n`, spec-defined to be ignored by any SSE client) sent on this
# cadence keeps the connection alive through any gap between node events
# (a single node -- e.g. USDA grounding lookups -- can occasionally run
# longer than a couple of seconds).
HEARTBEAT_INTERVAL_SECONDS = 10.0


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event. `data` is JSON-encoded on a single
    line -- SSE's `data:` field is newline-delimited, so it must never itself
    contain a bare newline."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_recommend(
    request: RecommendationRequest, session_user_id: str
) -> AsyncIterator[str]:
    run_id = get_run_id()
    sink = InMemorySink()
    sink_token = bind_sink_override(sink)
    sent = 0
    last_activity = time.monotonic()
    # Fire-and-run in a worker thread: run_recommendation_graph is the exact
    # function POST /recipes/recommend calls synchronously today, so the
    # response this eventually yields as the terminal `result` event is
    # byte-for-byte the same shape/logic, including its analytics capture
    # and user_id binding -- there is exactly one implementation of "run the
    # recommend graph and build a RecommendationResponse" in this codebase.
    task = asyncio.ensure_future(
        asyncio.to_thread(run_recommendation_graph, request, session_user_id)
    )
    try:
        while not task.done():
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            events = sink.get_events(run_id)
            if len(events) > sent:
                for event in events[sent:]:
                    yield _sse("node", event.model_dump(mode="json"))
                sent = len(events)
                last_activity = time.monotonic()
            elif time.monotonic() - last_activity >= HEARTBEAT_INTERVAL_SECONDS:
                yield ": heartbeat\n\n"
                last_activity = time.monotonic()

        # Drain any events that landed between the last poll and task
        # completion -- traced_node's final "finished"/"failed" RunEvent for
        # the last node to run is always emitted before
        # run_recommendation_graph returns or raises, so this is the last
        # chance to relay it before reading task.result()/exception().
        events = sink.get_events(run_id)
        for event in events[sent:]:
            yield _sse("node", event.model_dump(mode="json"))
    finally:
        # Client disconnect surfaces here as GeneratorExit thrown into this
        # generator at its current `await`/`yield` point -- this still runs
        # then. NOTE: the worker thread itself is not cancelled on
        # disconnect (Python threads aren't cooperatively cancellable); the
        # graph run completes in the background and its result is simply
        # never relayed. Accepted for this step -- no graph node has any
        # cancellation support to hook into, and a run that's already most
        # of the way through a 20-45s call is not worth aborting mid-flight.
        reset_sink_override(sink_token)

    try:
        response = task.result()
    except Exception as exc:
        # A mid-graph exception is NOT the same thing as one of
        # MacroChefState.errors's handled, user-facing cases (those already
        # surface inside a normal `result` event via response.errors) -- it
        # is an unhandled bug, exactly like an unhandled exception in the
        # synchronous POST /recipes/recommend, which FastAPI's default
        # handler turns into a generic 500 with no bespoke message
        # convention of its own to mirror here. This uses the same
        # `{"detail": ...}` shape every OTHER error response in this API
        # already uses (401/404/429) -- deliberately generic (never the raw
        # exception message) so this stream never becomes a second channel
        # that leaks internals a normal response wouldn't.
        yield _sse(
            "error",
            {"detail": "Internal Server Error", "error_type": type(exc).__name__},
        )
        return

    yield _sse("result", response.model_dump(mode="json"))


@router.post("/recommend/stream")
async def recommend_recipes_stream(
    request: RecommendationRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> StreamingResponse:
    """SSE variant of POST /recipes/recommend. Same request body, same
    session gate, same rate-limit bucket as the synchronous endpoint (this
    reuses `require_recommend_rate_limit` directly rather than a parallel
    bucket -- a client hammering either endpoint hits the same limit).

    Emits one `node` SSE event per `RunEvent` (started/finished/failed) as
    each graph node executes, an `: heartbeat` comment line roughly every
    10s of silence (see docs/DEPLOY.md), and ends with exactly one terminal
    event: `result` (a full `RecommendationResponse`, identical shape to
    what POST /recipes/recommend returns) or `error`.
    """
    return StreamingResponse(
        _stream_recommend(request, session_user_id),
        media_type="text/event-stream",
        headers={
            # Disables response buffering on nginx-style reverse proxies
            # that would otherwise batch chunks and defeat "live"
            # streaming; harmless if no such proxy is in the path.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
