"""SSE streaming of recommend-graph progress (ROADMAP.md Phase 3, Step 3.1),
extended by Step 3.2 to support a true HITL pause.

`POST /recipes/recommend/stream` is an ADDITIVE sibling of
`POST /recipes/recommend` (app.api.routes_recommendations) -- same request
body, same session gate, same rate-limit bucket -- that relays each graph
node's `RunEvent`s (app.observability.events) live as Server-Sent Events
while the run is in flight, instead of blocking silently for the 20-45s a
full run can take.

Architecture decision -- worker-thread + `InMemorySink` polling, NOT native
`graph.stream()`/`astream()`:

`get_compiled_macrochef_graph()` (app.graph.builder) returns either a real
compiled LangGraph `StateGraph` OR, if `langgraph` itself fails to import,
`SequentialMacroChefGraph` -- and this endpoint keeps working (with
per-node events) in the fallback case too. LangGraph's `.stream()` only
yields state deltas AFTER each superstep completes (no "started" boundary
without extra per-node callback plumbing), and has no equivalent at all on
the sequential fallback runner -- driving the SSE feed off it would mean
reinventing the "started" half of every event AND maintaining two separate
node->event translation code paths.

Instead: the graph invocation runs inside `asyncio.to_thread`, and this
module polls a per-request `InMemorySink` that every `@traced_node`-wrapped
node (already applied to all 11 recommend-graph nodes) writes into as it
executes -- uniformly, whether the underlying `.invoke()` is LangGraph's or
`SequentialMacroChefGraph`'s, since both share that call signature.
`asyncio.to_thread` copies this coroutine's `contextvars.Context` (see
`app.observability.events.bind_sink_override`) into the worker thread, so
this ONE request's events land in THIS request's sink, without touching the
process-wide default sink any other concurrent request uses.

ROADMAP.md Phase 3, Step 3.2 (advisor-reviewed integration decision) --
what changed and what didn't:

- **`langgraph` unavailable** (`get_compiled_macrochef_graph()` returns
  `SequentialMacroChefGraph`): UNCHANGED. Calls `run_recommendation_graph`
  exactly as before this step, ends in `result`/`error` only. This branch
  is mandatory, not optional -- it's the entire reason the polling
  architecture above exists (must survive `langgraph` failing to import),
  so it is never replaced by a 503.
- **`langgraph` available, no low-confidence image/mixed observation**:
  response-shape UNCHANGED -- ends in `result` with the identical
  `RecommendationResponse` the old code produced, provable by the fact
  that `build_recommendation_response` (app.graph.builder) is the same
  function both this path and the old one call. The only invisible-at-the-
  SSE-bytes-level difference is that this run now goes through the
  CHECKPOINTED graph (`app.api.routes_runs.invoke_hitl_graph`, mints a
  `thread_id` + `GraphRun` ownership row) instead of the uncheckpointed
  one -- a storage-growth consideration for never-interrupted runs, see
  docs/BACKLOG.md.
- **`langgraph` available, run pauses on a low-confidence image/mixed
  observation**: NEW terminal event `awaiting_input` (payload:
  `{"thread_id", "awaiting"}`, `awaiting` shaped identically to
  `RunStatusResponse.awaiting`, app.schemas.runs) instead of `result`.
  Node-level `node` events still relay live, right up through
  `inventory_confirmation_node`'s pause -- this comes for free from
  `traced_node`'s sink, indifferent to checkpointing. The connection then
  closes (SSE has no bidirectional resume path); the client calls the
  existing `POST /runs/{thread_id}/resume` (JSON, not streamed) to submit
  the correction and get the final plan. This is the literal "upload photo
  -> stream pauses -> confirm -> resume" README demo ROADMAP.md's Step 3.2
  acceptance criterion names.

`invoke_hitl_graph`/`status_from_invoke_result` (app.api.routes_runs) are
the SAME functions `POST /runs` uses -- there is exactly one thread-
minting/ownership code path and one interrupt-detection code path shared
by both entrypoints, never two that could silently diverge.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.routes_runs import invoke_hitl_graph, status_from_invoke_result
from app.dependencies import require_recommend_rate_limit
from app.graph.builder import (
    SequentialMacroChefGraph,
    get_compiled_macrochef_graph,
    run_recommendation_graph,
)
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

    # ROADMAP 3.2: only the checkpointed graph can ever pause -- the
    # sequential-fallback runner (langgraph unavailable) has no interrupt
    # mechanism at all, so it keeps calling run_recommendation_graph
    # exactly as before this step. `hitl_capable` decides both which
    # function this request's worker thread calls AND how the terminal
    # event below is built from its result.
    graph = get_compiled_macrochef_graph()
    hitl_capable = not isinstance(graph, SequentialMacroChefGraph)

    if hitl_capable:
        task = asyncio.ensure_future(
            asyncio.to_thread(invoke_hitl_graph, request, session_user_id)
        )
    else:
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
        # the last node to run is always emitted before the invoked function
        # returns or raises, so this is the last chance to relay it before
        # reading task.result()/exception().
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
        result = task.result()
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

    if not hitl_capable:
        # Sequential fallback: `result` is a RecommendationResponse object
        # directly, exactly as before ROADMAP 3.2.
        yield _sse("result", result.model_dump(mode="json"))
        return

    thread_id, invoke_result = result
    status = status_from_invoke_result(thread_id, invoke_result)
    if status.status == "awaiting_input":
        yield _sse("awaiting_input", {"thread_id": status.thread_id, "awaiting": status.awaiting})
        return
    yield _sse("result", status.result.model_dump(mode="json"))


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
    what POST /recipes/recommend returns), `awaiting_input` (ROADMAP 3.2 --
    the run paused on a low-confidence image/mixed inventory observation;
    resume via `POST /runs/{thread_id}/resume`), or `error`.
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
