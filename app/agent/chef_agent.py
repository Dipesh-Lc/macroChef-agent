"""The Chef agent's ReAct loop + deterministic response gate (ROADMAP.md
Phase 3, Step 3.3).

Architecture: a LangGraph two-node cycle (`llm_node` <-> `tools_node`, per
ROADMAP's own wording), plus a `gate_node` on the "the LLM thinks it's
done" exit path. Reuses `app.graph.builder._get_checkpointer()` (the ROADMAP
3.2 cached sqlite/Postgres checkpointer singleton) rather than building a
second one -- every `graph.invoke`/`get_state` call here passes a distinct
`checkpoint_ns="chef"` in its `configurable` dict so this graph's checkpoint
rows can never collide with the recommend graph's, even though both mint
`thread_id`s the same way (`secrets.token_urlsafe(16)`) and could otherwise
theoretically clash (advisor-reviewed decision, Q3/Q5 -- "free insurance").

Design call made beyond the advisor's Q1-Q5 decisions (flagged for the
follow-up review): the ReAct step schema (`ChefStep`) is a flat Pydantic
model with plain `str` fields (`step_type`, `tool`) rather than a
discriminated union of per-tool Pydantic models. `generate_structured`'s
mock-provider path (`model_provider._mock_schema_example`) fills a `Literal`/
enum-typed field with the literal string `"mock"`, which is never a valid
enum member -- a discriminated union built from `Literal["tool_call",
"final_answer"]` (etc.) would make every non-monkeypatched mock-provider
call fail Pydantic validation on the very first turn. Tool-specific argument
shapes are still fully Pydantic-validated -- just one layer down, in
`app.agent.tools.dispatch_tool_call` (via `TOOL_ARGS_ADAPTER`, a real
discriminated union) -- so CLAUDE.md invariant #4 ("Pydantic contracts for
all agent node inputs/outputs") holds throughout; this only changes WHERE in
the pipeline the union is enforced.

Cross-turn persistence: the authoritative conversation history is SQL
`ChatMessage` rows (`app.agent.memory`), not the LangGraph checkpoint's own
persisted state -- `run_chef_turn` reconstructs a full state at the start of
every turn (`memory.load_transcript`) rather than relying on LangGraph's
implicit partial-dict merge semantics for a non-reducer Pydantic state
schema (the same "every node returns a full dict, merge is last-write-wins
per key" model `app.graph.state.MacroChefState` already uses -- correct for
overwrite semantics, but not for list-accumulation across SEPARATE
`invoke()` calls without a reducer). The checkpointer is still genuinely
used (satisfies the "reuse app.graph.builder._get_checkpointer()" mandate,
and namespaces this graph's per-turn scratch state, e.g. mid-turn tool-call
history, apart from the recommend graph's); SQL is simply the more
auditable source of truth for cross-turn history, matching the "GET
/chat/{thread_id} returns thread status/history" requirement directly.
"""

from __future__ import annotations

import threading
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.memory import ToolCallLogEntry, TranscriptEntry, load_transcript, persist_turn
from app.agent.prompts import (
    CORRECTION_MISSING_SAFETY_CHECK,
    CORRECTION_NO_TOOL_CALLED,
    FALLBACK_MESSAGE,
    SYSTEM_PROMPT,
    wrap_tool_output,
)
from app.agent.tools import TOOL_NAMES, ToolContext, dispatch_tool_call
from app.config import Settings, get_settings
from app.schemas.user import UserProfile
from app.services.model_provider import generate_structured, provider_chain
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Hard cap on tool-call round-trips within a single turn -- guards against a
# runaway loop (a misbehaving/mock LLM that never emits a final_answer step)
# ever hanging a chat turn indefinitely. Generous enough for a real
# multi-tool turn (search -> check safety -> ground nutrition -> respond)
# with headroom, tight enough to fail fast in a pathological case.
MAX_TOOL_ITERATIONS = 6


# ---------------------------------------------------------------------------
# ReAct step schema
# ---------------------------------------------------------------------------


class ChefStep(BaseModel):
    """One LLM turn's decision: call a tool, or answer the user. See this
    module's docstring for why this is a flat schema (plain `str` fields)
    rather than a discriminated union at this layer."""

    step_type: str = "final_answer"
    tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None


def _generate_chef_step(prompt: str, settings: Settings) -> ChefStep:
    """Drive `generate_structured` across the configured provider chain
    (mirrors `model_provider.generate_detailed_instructions_with_provider_
    chain`'s own provider-chain loop) -- ALL LLM calls for this loop go
    through `generate_structured`, never inline HTTP (CLAUDE.md invariant
    #5). A structurally-invalid step (bad `step_type`, unknown `tool`) is
    treated the same as a provider failure: try the next provider in the
    chain. If every provider (including the always-present final "mock"
    entry) fails, fail closed to a safe apology final_answer rather than
    raising out of the graph node."""
    last_error: Exception | None = None
    for provider in provider_chain(settings):
        try:
            step = generate_structured(provider, prompt, ChefStep, settings, purpose="chef_agent")
            if step.step_type not in ("tool_call", "final_answer"):
                raise ValueError(f"unrecognized step_type {step.step_type!r}")
            if step.step_type == "tool_call" and step.tool not in TOOL_NAMES:
                raise ValueError(f"unrecognized tool {step.tool!r}")
            return step
        except Exception as exc:  # noqa: BLE001 - fall through to the next provider
            last_error = exc
            logger.warning("Chef agent step generation failed for provider %s: %s", provider, exc)

    logger.error(
        "Chef agent step generation failed for every provider in the chain: %s", last_error
    )
    return ChefStep(step_type="final_answer", content=FALLBACK_MESSAGE)


def _build_prompt(state: ChefState) -> str:
    lines = [SYSTEM_PROMPT, "", "## Conversation so far"]
    for entry in state.transcript:
        if entry.role == "user":
            lines.append(f"User: {entry.content}")
        elif entry.role == "assistant":
            lines.append(f"Assistant: {entry.content}")
        elif entry.role == "system":
            lines.append(f"[SYSTEM CORRECTION]: {entry.content}")
        else:  # "tool" -- already delimited by wrap_tool_output
            lines.append(entry.content)
    lines.append("")
    lines.append(
        "Respond with a single JSON object, either "
        '{"step_type": "tool_call", "tool": "<tool name>", "tool_args": {...}} or '
        '{"step_type": "final_answer", "content": "<your reply to the user>"}.'
    )
    return "\n".join(lines)


def _args_summary(tool: str | None, args: dict[str, Any]) -> str:
    """Short human string for the UI's tool-call chip (SSE `tool_call`
    event's `args_summary`) -- never the full payload, mirrors `RunEvent.
    summary`'s "one human sentence" convention (ROADMAP 1.1)."""
    if tool == "check_recipe_safety":
        return f"Checking safety of {len(args.get('recipe_ids') or [])} recipe(s)."
    if tool == "search_recipes":
        return "Searching recipes."
    if tool == "ground_nutrition":
        return "Checking nutrition."
    if tool == "propose_substitutions":
        return f"Finding substitutions for {args.get('recipe_id')}."
    if tool == "build_day_plan":
        return "Building a day plan."
    if tool == "get_user_context":
        return "Reading your saved preferences."
    if tool == "remember":
        return "Remembering a note."
    return f"Calling {tool}."


# ---------------------------------------------------------------------------
# Response gate (spec section 2.6) -- a pure function, unit-testable in
# isolation from the LLM.
# ---------------------------------------------------------------------------


class GateResult(BaseModel):
    passed: bool
    reason: str | None = None
    uncovered_recipe_ids: list[str] = Field(default_factory=list)


def _candidate_recipe_titles(tool_call_log: list[ToolCallLogEntry]) -> dict[str, str]:
    """Every (recipe_id -> title) pair this turn's tool outputs surfaced --
    from `search_recipes`, `propose_substitutions`, and `build_day_plan`
    results. Used only to detect whether the draft response NAMES a recipe
    (by title) that was surfaced this turn; never used to decide safety."""
    titles: dict[str, str] = {}
    for entry in tool_call_log:
        for recipe in entry.raw.get("recipes", []) or []:
            recipe_id, title = recipe.get("recipe_id"), recipe.get("title")
            if recipe_id and title:
                titles[recipe_id] = title
        for variant in entry.raw.get("variants", []) or []:
            recipe_id, title = variant.get("recipe_id"), variant.get("title")
            if recipe_id and title:
                titles[recipe_id] = title
        for item in entry.raw.get("items", []) or []:
            recipe_id, title = item.get("recipe_id"), item.get("title")
            if recipe_id and title:
                titles[recipe_id] = title
    return titles


def evaluate_response_gate(
    tool_call_log: list[ToolCallLogEntry], draft_response: str
) -> GateResult:
    """Deterministic post-check (never a second opinion asked of the LLM):
    scans the turn's tool-call history for every `check_recipe_safety`
    call's VALID `recipe_id`s, and the turn's other tool outputs for every
    recipe_id+title the draft response could plausibly be naming. Blocks
    (passed=False) if the draft text mentions a candidate recipe's title
    whose recipe_id was never confirmed valid by a `check_recipe_safety`
    call this turn, OR if no tool was called at all this turn.

    Advisor Q1 (batch semantics): `check_recipe_safety` is batch-capable
    (`app.agent.tools.CheckRecipeSafetyArgs.recipe_ids`), so a single call
    can cover an entire turn's worth of recipes -- this function's coverage
    check is `mentioned_recipe_ids - covered_recipe_ids` across the UNION of
    every `check_recipe_safety` call this turn, exactly the Q1-resolved
    rule.

    Two bypasses found and closed by the second FULL TREATMENT review (both
    were real, both let an unverified/contradicted recipe recommendation
    through untouched -- see that review's findings for the full rationale):

    1. **Zero-tool-call bypass.** A turn with an empty `tool_call_log` has no
       candidate titles to check against at all, so the old logic passed it
       unconditionally -- a model could invent a recipe from parametric
       knowledge, calling no tool whatsoever, and the "backstop" would never
       engage. Now: an empty `tool_call_log` fails the gate outright, so
       every substantive turn is forced through at least one tool
       round-trip (cheap for genuinely tool-free turns like "hi" -- one
       extra `get_user_context()`-style call is the accepted cost of a
       backstop that doesn't depend on the LLM's cooperation).
    2. **Checked-but-contradicted bypass.** Coverage used to mean "a
       `check_recipe_safety` call touched this recipe_id," regardless of
       its verdict -- so a recipe explicitly found `is_valid=False` (an
       allergy/diet violation) still counted as "covered" if the model then
       asserted it was safe anyway. Coverage now reuses the already-tested
       `_verified_safe_recipe_ids` helper (checked AND `is_valid=True`),
       the exact same "trusted subset" `build_day_plan`'s tool wrapper
       already relies on -- a rejected recipe can never satisfy the gate no
       matter how many times it was checked.
    """
    if not tool_call_log:
        return GateResult(
            passed=False,
            reason="No tool was called this turn before answering.",
        )

    covered = _verified_safe_recipe_ids(tool_call_log)

    candidate_titles = _candidate_recipe_titles(tool_call_log)
    lowered_response = draft_response.lower()
    mentioned = {
        recipe_id
        for recipe_id, title in candidate_titles.items()
        if title and title.lower() in lowered_response
    }
    uncovered = sorted(mentioned - covered)
    if uncovered:
        return GateResult(
            passed=False,
            reason=(
                f"Recipe(s) {uncovered} were mentioned in the response without a "
                "check_recipe_safety call confirming them safe this turn."
            ),
            uncovered_recipe_ids=uncovered,
        )
    return GateResult(passed=True)


def _verified_safe_recipe_ids(tool_call_log: list[ToolCallLogEntry]) -> frozenset[str]:
    """recipe_ids `check_recipe_safety` validated as `is_valid=True` this
    turn -- what `build_day_plan`'s tool wrapper is allowed to plan around
    (spec: assemble_plan itself does no safety filtering, the wrapper must)."""
    safe: set[str] = set()
    for entry in tool_call_log:
        if entry.tool != "check_recipe_safety":
            continue
        for result in entry.raw.get("results", []) or []:
            verdict = result.get("result") or {}
            recipe_id = result.get("recipe_id")
            if recipe_id and verdict.get("is_valid"):
                safe.add(recipe_id)
    return frozenset(safe)


# ---------------------------------------------------------------------------
# Live SSE event relay (mirrors app.observability.events' InMemorySink /
# sink-override contextvar pattern, ROADMAP 3.1) -- kept local to this
# package (not the observability module) since these are chat-specific
# `tool_call`/`tool_result` UI events, a different vocabulary from `RunEvent`.
# ---------------------------------------------------------------------------


class ChatEvent(BaseModel):
    event: Literal["tool_call", "tool_result"]
    data: dict[str, Any]


class ChatEventSink:
    """Per-request event buffer `app.api.routes_chat`'s SSE generator polls
    while `run_chef_turn` executes in a worker thread -- same shape as
    `app.observability.events.InMemorySink`, purpose-built for the chat
    event vocabulary instead."""

    def __init__(self) -> None:
        self._events: list[ChatEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: ChatEvent) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[ChatEvent]:
        with self._lock:
            return list(self._events)


_CHAT_EVENT_SINK_CTX: ContextVar[ChatEventSink | None] = ContextVar(
    "chef_chat_event_sink", default=None
)


def bind_chat_event_sink(sink: ChatEventSink) -> Token:
    return _CHAT_EVENT_SINK_CTX.set(sink)


def reset_chat_event_sink(token: Token) -> None:
    _CHAT_EVENT_SINK_CTX.reset(token)


def _emit_chat_event(event: Literal["tool_call", "tool_result"], data: dict[str, Any]) -> None:
    sink = _CHAT_EVENT_SINK_CTX.get()
    if sink is not None:
        sink.emit(ChatEvent(event=event, data=data))


# ---------------------------------------------------------------------------
# Graph state + nodes
# ---------------------------------------------------------------------------


class ChefState(BaseModel):
    thread_id: str
    user_id: str
    user_profile: dict[str, Any]
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    tool_call_log: list[ToolCallLogEntry] = Field(default_factory=list)
    iteration: int = 0
    gate_retries: int = 0
    pending_tool: str | None = None
    pending_tool_args: dict[str, Any] = Field(default_factory=dict)
    final_answer: str | None = None
    done: bool = False


def ensure_chef_state(state: ChefState | dict) -> ChefState:
    if isinstance(state, ChefState):
        return state
    return ChefState.model_validate(state)


def _state_update(state: ChefState, **updates: Any) -> dict[str, Any]:
    data = state.model_dump()
    data.update(updates)
    return data


def llm_node(state: ChefState | dict) -> dict:
    current = ensure_chef_state(state)
    settings = get_settings()
    prompt = _build_prompt(current)
    step = _generate_chef_step(prompt, settings)

    new_transcript = list(current.transcript)
    if step.step_type == "tool_call" and step.tool:
        new_transcript.append(
            TranscriptEntry(role="assistant", content=f"(calling {step.tool})", tool=step.tool)
        )
        return _state_update(
            current,
            transcript=new_transcript,
            pending_tool=step.tool,
            pending_tool_args=step.tool_args,
            final_answer=None,
        )

    content = step.content or ""
    new_transcript.append(TranscriptEntry(role="assistant", content=content))
    return _state_update(
        current,
        transcript=new_transcript,
        pending_tool=None,
        pending_tool_args={},
        final_answer=content,
    )


def tools_node(state: ChefState | dict) -> dict:
    current = ensure_chef_state(state)
    ctx = ToolContext(
        user_id=current.user_id, user_profile=UserProfile.model_validate(current.user_profile)
    )
    verified_safe = _verified_safe_recipe_ids(current.tool_call_log)
    tool_name = current.pending_tool or "unknown"
    call_id = uuid.uuid4().hex

    _emit_chat_event(
        "tool_call",
        {
            "tool": tool_name,
            "args_summary": _args_summary(current.pending_tool, current.pending_tool_args),
            "call_id": call_id,
        },
    )
    result = dispatch_tool_call(
        ctx, tool_name, current.pending_tool_args, verified_safe_recipe_ids=verified_safe
    )
    _emit_chat_event(
        "tool_result", {"call_id": call_id, "summary": result.summary, "raw": result.raw}
    )

    wrapped = wrap_tool_output(tool_name, result.model_dump())
    new_transcript = list(current.transcript) + [
        TranscriptEntry(role="tool", content=wrapped, tool=tool_name)
    ]
    log_entry = ToolCallLogEntry(
        tool=tool_name,
        args=current.pending_tool_args,
        ok=result.ok,
        summary=result.summary,
        raw=result.raw,
        error=result.error,
        recipe_ids_covered=result.recipe_ids_covered,
    )
    new_log = list(current.tool_call_log) + [log_entry]
    return _state_update(
        current,
        transcript=new_transcript,
        tool_call_log=new_log,
        iteration=current.iteration + 1,
        pending_tool=None,
        pending_tool_args={},
    )


def gate_node(state: ChefState | dict) -> dict:
    current = ensure_chef_state(state)

    if current.final_answer is None:
        # The tool-call budget ran out without the LLM ever producing a
        # final_answer step -- fail closed rather than looping forever or
        # shipping an empty response.
        logger.error(
            "Chef agent thread %s exhausted its tool-call budget without a final answer.",
            current.thread_id,
        )
        return _state_update(current, final_answer=FALLBACK_MESSAGE, done=True)

    gate = evaluate_response_gate(current.tool_call_log, current.final_answer)
    if gate.passed:
        return _state_update(current, done=True)

    if current.gate_retries >= 1:
        # Second failure in a row -- block-and-fallback, never silently
        # strip the recipe mention and ship a doctored response (spec
        # 2.6). This is a bug in agent behavior, surfaced loudly.
        logger.error(
            "Chef agent response gate blocked thread %s twice in a row: %s",
            current.thread_id,
            gate.reason,
        )
        return _state_update(current, final_answer=FALLBACK_MESSAGE, done=True)

    correction = (
        CORRECTION_NO_TOOL_CALLED
        if not gate.uncovered_recipe_ids
        else CORRECTION_MISSING_SAFETY_CHECK.format(
            recipe_ids=", ".join(gate.uncovered_recipe_ids)
        )
    )
    new_transcript = list(current.transcript) + [TranscriptEntry(role="system", content=correction)]
    return _state_update(
        current,
        transcript=new_transcript,
        gate_retries=current.gate_retries + 1,
        final_answer=None,
        done=False,
    )


def after_llm(state: ChefState | dict) -> str:
    current = ensure_chef_state(state)
    if current.pending_tool and current.iteration < MAX_TOOL_ITERATIONS:
        return "tools"
    return "gate"


def after_gate(state: ChefState | dict) -> str:
    current = ensure_chef_state(state)
    return "end" if current.done else "retry"


# ---------------------------------------------------------------------------
# Graph assembly -- mirrors app.graph.builder's narrow-except-around-the-
# import-only pattern (app.graph.library_builder's convention, adopted by
# ROADMAP 3.1 for the recommend graph too): anything past a missing
# `langgraph` package is a real bug and must raise, never silently degrade.
# ---------------------------------------------------------------------------


def _wire_chef_graph(graph, start, end):
    graph.add_node("llm_node", llm_node)
    graph.add_node("tools_node", tools_node)
    graph.add_node("gate_node", gate_node)

    graph.add_edge(start, "llm_node")
    graph.add_conditional_edges("llm_node", after_llm, {"tools": "tools_node", "gate": "gate_node"})
    graph.add_edge("tools_node", "llm_node")
    graph.add_conditional_edges("gate_node", after_gate, {"retry": "llm_node", "end": end})
    return graph


class SequentialChefGraph:
    """Fallback runner used only if `langgraph` itself fails to import --
    mirrors `app.graph.builder.SequentialMacroChefGraph`'s role exactly, same
    node order the LangGraph wiring above encodes."""

    def invoke(self, initial_state: dict, config: dict | None = None) -> dict:
        del config  # no checkpointing on this fallback path
        state = llm_node(initial_state)
        while True:
            if after_llm(state) == "tools":
                state = tools_node(state)
                state = llm_node(state)
                continue
            state = gate_node(state)
            if after_gate(state) == "end":
                return state
            state = llm_node(state)


def get_compiled_chef_graph():
    """Checkpointed chef graph, reusing `app.graph.builder._get_checkpointer()`
    (advisor Q3/Q5) -- NOT `@lru_cache`d, same reasoning as `app.graph.
    builder.get_compiled_macrochef_graph`'s docstring: `add_node` captures
    node function references at compile time, so a cached singleton would
    freeze in whatever `llm_node`/`tools_node` resolved to at first build,
    breaking a test's monkeypatch of this module's own node functions. The
    checkpointer connection itself IS cached (inside `_get_checkpointer`),
    so this stays cheap to call per turn.

    Returns `None` (not `SequentialChefGraph()`) when `langgraph` is
    unavailable, so callers (`run_chef_turn`) can choose the sequential
    fallback explicitly -- mirrors `app.graph.builder.build_macrochef_graph`'s
    own narrowed-except-around-the-import pattern.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return None

    from app.graph.builder import _get_checkpointer

    graph = _wire_chef_graph(StateGraph(ChefState), START, END)
    return graph.compile(checkpointer=_get_checkpointer())


def chef_thread_config(thread_id: str) -> dict:
    """`checkpoint_ns="chef"` partitions this graph's checkpoint rows from
    the recommend graph's (`app.api.routes_runs.thread_config`), even though
    both mint `thread_id`s via `secrets.token_urlsafe(16)` and could
    otherwise theoretically collide (advisor-reviewed decision, Q3/Q5)."""
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": "chef"}}


@dataclass
class ChefTurnResult:
    assistant_message: str
    tool_calls: list[dict[str, Any]]


def run_chef_turn(
    thread_id: str, user_id: str, user_profile: UserProfile, user_message: str
) -> ChefTurnResult:
    """Runs one full turn of the Chef agent for an already-owned thread
    (`app.api.routes_chat` checks ownership before calling this). Reconstructs
    the thread's prior conversation from SQL (`app.agent.memory.
    load_transcript` -- see this module's docstring for why SQL, not the
    checkpoint, is the cross-turn source of truth), appends the new user
    message, drives the ReAct loop to completion, persists the turn, and
    returns the assistant's final answer + this turn's tool-call history.

    Safe to call from a plain synchronous context only (no already-running
    asyncio event loop) -- `app.agent.tools.ground_nutrition`'s handler calls
    `asyncio.run()` internally. `app.api.routes_chat` always calls this via
    `asyncio.to_thread`, matching `app.api.routes_stream`'s identical
    worker-thread architecture.
    """
    prior_transcript = load_transcript(thread_id)
    transcript = [*prior_transcript, TranscriptEntry(role="user", content=user_message)]

    initial_state = ChefState(
        thread_id=thread_id,
        user_id=user_id,
        user_profile=user_profile.model_dump(),
        transcript=transcript,
    )

    graph = get_compiled_chef_graph()
    config = chef_thread_config(thread_id)
    if graph is not None:
        result = graph.invoke(initial_state.model_dump(), config=config)
    else:
        result = SequentialChefGraph().invoke(initial_state.model_dump(), config=config)

    final_state = ensure_chef_state(result)
    persist_turn(
        thread_id,
        user_message,
        final_state.final_answer or FALLBACK_MESSAGE,
        final_state.tool_call_log,
    )

    return ChefTurnResult(
        assistant_message=final_state.final_answer or FALLBACK_MESSAGE,
        tool_calls=[entry.model_dump() for entry in final_state.tool_call_log],
    )
