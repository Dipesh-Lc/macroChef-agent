"""ROADMAP.md Phase 3, Step 3.2 -- true LangGraph checkpointer + HITL
inventory confirmation.

Additive sibling of `app.api.routes_recommendations`: `POST
/recipes/recommend` is UNCHANGED (still calls `run_recommendation_graph`,
which runs the uncheckpointed `app.graph.builder.build_macrochef_graph()`
singleton to completion every time -- `MacroChefState.hitl_enabled`
defaults False and that endpoint never sets it, so
`inventory_confirmation_node` can never pause there; see that field's and
node's docstrings).

`POST /recipes/recommend/stream` (`app.api.routes_stream`) is different:
ROADMAP.md's own Step 3.2 acceptance criterion requires that endpoint to
itself emit an `awaiting_input` SSE event when a run pauses (the literal
"upload photo -> stream pauses -> confirm -> resume" README demo). Its
non-interrupting response (no low-confidence image observation, or
`langgraph` unavailable) is unchanged -- see that module's docstring for
the exact branching. `invoke_hitl_graph`/`require_langgraph_runtime`/
`thread_config`/`status_from_invoke_result` below are the shared internal
helpers both this router and `routes_stream` call, so there is exactly one
thread-minting/ownership code path, never two that could silently
diverge.

Ownership: every `thread_id` is bound to the minting user's verified
session identity in `app.data.models.GraphRun` (never the checkpointer
itself, which has no concept of an owning user) at creation time.
`get_run`/`resume_run` check that mapping FIRST, before ever touching the
checkpointer, and return 404 -- not 403 -- for both "no such thread_id" and
"thread_id exists, belongs to someone else" (advisor-reviewed decision:
mirrors `app.services.share_service.get_share`'s existing "no oracle for
exists-but-not-yours" collapse; thread_ids already carry 128 bits of
unguessability via `secrets.token_urlsafe`, so hiding existence costs
little, and no legitimate client needs to tell the two cases apart).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException

from app.data.graph_run_repository import GraphRunRepository
from app.dependencies import get_session_user, require_recommend_rate_limit
from app.graph.builder import (
    SequentialMacroChefGraph,
    build_recommendation_response,
    get_compiled_macrochef_graph,
    request_to_state,
)
from app.graph.state import ensure_state
from app.observability.events import bind_user_id, reset_user_id
from app.schemas.recommendation import RecommendationRequest
from app.schemas.runs import ResumeRunRequest, RunStatusResponse

router = APIRouter(prefix="/runs", tags=["runs"])

# Opaque thread id length -- 128 bits, matching the house pattern used for
# every other opaque public id in this codebase (app.services.share_service's
# _SHARE_ID_BYTES, frontend/session_client.py's session id). Deliberately
# NOT a sequential integer (enumerable) and NOT UUID4 (weaker randomness
# guarantee than `secrets`).
_THREAD_ID_BYTES = 16


def require_langgraph_runtime():
    graph = get_compiled_macrochef_graph()
    if isinstance(graph, SequentialMacroChefGraph):
        # Only reachable if the `langgraph` package itself failed to import
        # (see get_compiled_macrochef_graph's own narrowed except) -- unlike
        # the old sync/stream endpoints, this feature has no non-LangGraph
        # fallback: a true pause/resume needs a real checkpointer. Surfaced
        # loudly (503), never silently degraded to a run that can never
        # actually pause.
        raise HTTPException(
            status_code=503,
            detail=(
                "HITL runs require the LangGraph runtime, which is unavailable in this deployment."
            ),
        )
    return graph


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def status_from_invoke_result(thread_id: str, result: dict) -> RunStatusResponse:
    interrupts = result.get("__interrupt__")
    if interrupts:
        return RunStatusResponse(
            thread_id=thread_id, status="awaiting_input", awaiting=interrupts[0].value
        )
    final_state = ensure_state(result)
    return RunStatusResponse(
        thread_id=thread_id, status="completed", result=build_recommendation_response(final_state)
    )


def invoke_hitl_graph(request: RecommendationRequest, user_id: str) -> tuple[str, dict]:
    """Mints a `thread_id`, records its ownership row, and invokes the
    checkpointed graph once with `hitl_enabled=True`. Shared by `start_run`
    below and `app.api.routes_stream`'s HITL streaming branch -- factored
    out so there is exactly ONE place that mints a thread_id/ownership row,
    never two independently-maintained copies that could silently diverge
    (e.g. one forgetting the ownership row, reopening the cross-user-resume
    gap invariant #3 exists to close). Callers must have already confirmed
    the LangGraph runtime is available (`require_langgraph_runtime`) --
    this function assumes `graph` is a real checkpointed graph, not
    `SequentialMacroChefGraph`.
    """
    graph = require_langgraph_runtime()
    thread_id = secrets.token_urlsafe(_THREAD_ID_BYTES)
    GraphRunRepository().create(thread_id, user_id)

    user_id_token = bind_user_id(user_id)
    try:
        state = request_to_state(request, user_id, hitl_enabled=True)
        result = graph.invoke(state.model_dump(), config=thread_config(thread_id))
    finally:
        reset_user_id(user_id_token)
    return thread_id, result


@router.post("", response_model=RunStatusResponse)
def start_run(
    request: RecommendationRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> RunStatusResponse:
    """Mints a new `thread_id` bound to the verified session identity,
    invokes the checkpointed graph once, and returns either
    `status="awaiting_input"` (inventory_confirmation_node paused on a
    low-confidence image/mixed observation -- resume via
    `POST /runs/{thread_id}/resume`) or `status="completed"` (identical
    `RecommendationResponse` shape to `POST /recipes/recommend`, just
    wrapped)."""
    thread_id, result = invoke_hitl_graph(request, session_user_id)
    return status_from_invoke_result(thread_id, result)


@router.get("/{thread_id}", response_model=RunStatusResponse)
def get_run(thread_id: str, session_user_id: str = Depends(get_session_user)) -> RunStatusResponse:
    """Reads the current run status WITHOUT re-running the graph -- proves
    an interrupted run's state actually persisted in the checkpointer
    (tests/test_hitl_resume.py case 1)."""
    if GraphRunRepository().get_owned(thread_id, session_user_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    graph = require_langgraph_runtime()
    snapshot = graph.get_state(thread_config(thread_id))
    if snapshot.next:
        interrupts = [value for task in snapshot.tasks for value in task.interrupts]
        awaiting = interrupts[0].value if interrupts else None
        return RunStatusResponse(thread_id=thread_id, status="awaiting_input", awaiting=awaiting)

    final_state = ensure_state(snapshot.values)
    return RunStatusResponse(
        thread_id=thread_id, status="completed", result=build_recommendation_response(final_state)
    )


@router.post("/{thread_id}/resume", response_model=RunStatusResponse)
def resume_run(
    thread_id: str,
    request: ResumeRunRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> RunStatusResponse:
    """Resumes an interrupted run with the human-corrected inventory. The
    ownership check happens FIRST, before the checkpointer is ever touched
    -- a thread_id minted by user A is never readable or resumable by user
    B (tests/test_hitl_resume.py case 3)."""
    if GraphRunRepository().get_owned(thread_id, session_user_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    graph = require_langgraph_runtime()
    from langgraph.types import Command

    resume_payload = [item.model_dump(mode="json") for item in request.confirmed_inventory]

    user_id_token = bind_user_id(session_user_id)
    try:
        result = graph.invoke(Command(resume=resume_payload), config=thread_config(thread_id))
    finally:
        reset_user_id(user_id_token)

    return status_from_invoke_result(thread_id, result)
