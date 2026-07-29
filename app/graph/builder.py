from functools import lru_cache

from app.config import get_settings
from app.graph.edges import (
    after_fallback,
    after_intake,
    after_inventory_confirmation,
    after_safety_filter,
)
from app.graph.nodes import (
    constraint_builder_node,
    fallback_relaxation_node,
    intake_node,
    inventory_confirmation_node,
    meal_ranking_node,
    memory_update_node,
    nutrition_scoring_node,
    procurement_node,
    recipe_retriever_node,
    safety_filter_node,
    substitution_node,
)
from app.graph.state import MacroChefState, ensure_state
from app.observability.events import bind_user_id, reset_user_id
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.analytics import get_analytics


class SequentialMacroChefGraph:
    """Fallback runner with the same node order as the LangGraph workflow."""

    def invoke(self, initial_state: dict) -> dict:
        state = intake_node(initial_state)
        if after_intake(state) == "end":
            return state
        state = inventory_confirmation_node(state)
        if after_inventory_confirmation(state) == "end":
            return state

        for node in [constraint_builder_node, recipe_retriever_node, safety_filter_node]:
            state = node(state)

        if after_safety_filter(state) == "fallback_relaxation":
            state = fallback_relaxation_node(state)
            if after_fallback(state) == "end":
                return state

        # Phase 3: deterministic substitution engine, placed after safety_
        # filter_node (and fallback_relaxation_node when it ran) and before
        # nutrition_scoring_node -- see app.graph.nodes.substitution_node.
        state = substitution_node(state)

        for node in [
            nutrition_scoring_node,
            meal_ranking_node,
            procurement_node,
            memory_update_node,
        ]:
            state = node(state)
        return state


def _wire_graph(graph, start, end):
    # ROADMAP 3.1: narrowed from a bare `try: <entire build+compile> except
    # Exception: return SequentialMacroChefGraph()` to wrap ONLY the import
    # at each call site below, matching app.graph.library_builder.
    # build_library_discovery_graph's existing pattern. The old broad `try`
    # silently swallowed ANY error during graph construction (a typo in an
    # edge label, a node-signature mismatch, a `StateGraph`/`graph.compile()`
    # bug) with zero logging, silently degrading every request to the
    # untraced-by-LangGraph sequential fallback runner. A missing/broken
    # `langgraph` import is the only case that should fall back quietly;
    # anything else in graph construction -- including everything this
    # function does -- is a real bug that must raise, so this function
    # itself does no exception handling of its own.
    graph.add_node("intake_node", intake_node)
    graph.add_node("inventory_confirmation_node", inventory_confirmation_node)
    graph.add_node("constraint_builder_node", constraint_builder_node)
    graph.add_node("recipe_retriever_node", recipe_retriever_node)
    graph.add_node("safety_filter_node", safety_filter_node)
    graph.add_node("fallback_relaxation_node", fallback_relaxation_node)
    # Phase 3: deterministic substitution engine -- see app.graph.nodes.
    # substitution_node's docstring. Wired below (via the "nutrition_
    # scoring" conditional-edge label) after safety_filter_node/
    # fallback_relaxation_node, before nutrition_scoring_node.
    graph.add_node("substitution_node", substitution_node)
    graph.add_node("nutrition_scoring_node", nutrition_scoring_node)
    graph.add_node("meal_ranking_node", meal_ranking_node)
    graph.add_node("procurement_node", procurement_node)
    graph.add_node("memory_update_node", memory_update_node)

    graph.add_edge(start, "intake_node")
    graph.add_conditional_edges(
        "intake_node",
        after_intake,
        {"inventory_confirmation": "inventory_confirmation_node", "end": end},
    )
    graph.add_conditional_edges(
        "inventory_confirmation_node",
        after_inventory_confirmation,
        {"constraint_builder": "constraint_builder_node", "end": end},
    )
    graph.add_edge("constraint_builder_node", "recipe_retriever_node")
    graph.add_edge("recipe_retriever_node", "safety_filter_node")
    graph.add_conditional_edges(
        "safety_filter_node",
        after_safety_filter,
        {
            "fallback_relaxation": "fallback_relaxation_node",
            "nutrition_scoring": "substitution_node",
            "end": end,
        },
    )
    graph.add_conditional_edges(
        "fallback_relaxation_node",
        after_fallback,
        {"nutrition_scoring": "substitution_node", "end": end},
    )
    graph.add_edge("substitution_node", "nutrition_scoring_node")
    graph.add_edge("nutrition_scoring_node", "meal_ranking_node")
    graph.add_edge("meal_ranking_node", "procurement_node")
    graph.add_edge("procurement_node", "memory_update_node")
    graph.add_edge("memory_update_node", end)
    return graph


def _select_checkpointer(database_url: str):
    """Derive a LangGraph checkpointer from the same `DATABASE_URL` the rest
    of the app uses -- never a separate env var (ROADMAP.md Phase 3, Step
    3.2; advisor-reviewed decision). Mirrors the identical sqlite/Postgres
    dialect switch ROADMAP 5.2 already applied to
    `app.rag.vector_store.get_vector_store` and
    `app.services.rate_limiter.get_rate_limiter`.

    Checkpointer tables (`checkpoints`, `checkpoint_writes`, ...) are
    created and versioned by the upstream `langgraph-checkpoint-sqlite` /
    `langgraph-checkpoint-postgres` packages via their own `.setup()`
    migrations -- deliberately kept OUTSIDE this app's Alembic migrations.
    Hand-copying that DDL into our own migration would silently drift the
    moment the upstream package's internal schema changes on a version
    bump, and Step 5.1's schema-drift gate (`alembic check`) diffs the live
    DB against `Base.metadata`, which never needs to see these tables
    either way -- `.setup()` is startup infra init, the same category as
    `app.dependencies.validate_session_secret_at_startup`, not schema this
    app owns. Contrast `app.data.models.GraphRun` (thread_id -> owner
    mapping), which IS this app's own data and does go through Alembic --
    see alembic/versions/0004_graph_runs.py.
    """
    normalized = database_url
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://"):]

    if normalized.startswith("sqlite"):
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
        from sqlalchemy.engine import make_url

        # A real file path (never :memory:) so a paused run survives a
        # process restart -- see tests/test_hitl_resume.py's
        # process-restart case. `check_same_thread=False` + SqliteSaver's
        # own internal threading.Lock (verified against the installed
        # langgraph-checkpoint-sqlite version) is the same safe-sharing
        # pattern app.data.db's own sqlite engine already uses, for the
        # same reason: FastAPI serves sync routes from a thread pool.
        db_path = make_url(normalized).database or "./macrochef.db"
        conn = sqlite3.connect(db_path, check_same_thread=False)
        saver = SqliteSaver(conn)
    else:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        # Mirrors PostgresSaver.from_conn_string's own connection
        # parameters exactly, just without its context-manager form --
        # this connection must outlive the singleton, not close when a
        # `with` block exits.
        conn = Connection.connect(
            normalized, autocommit=True, prepare_threshold=0, row_factory=dict_row
        )
        saver = PostgresSaver(conn)

    saver.setup()
    return saver


@lru_cache(maxsize=1)
def _get_checkpointer():
    """The long-lived, connection-holding part of the checkpointed graph,
    cached separately from `get_compiled_macrochef_graph` below (which is
    deliberately NOT cached -- see that function's docstring). Caching only
    the checkpointer/connection here -- not the compiled graph -- gets both
    properties at once: the expensive resource (a DB connection, and for
    Postgres a one-time `.setup()` migration) is opened exactly once per
    process, while every call to `get_compiled_macrochef_graph()` still
    re-wires fresh node references, so a test's monkeypatch of e.g.
    `builder_module.recipe_retriever_node` is picked up immediately, the
    same guarantee `build_macrochef_graph`'s docstring explains for the
    uncheckpointed graph.
    """
    return _select_checkpointer(get_settings().database_url)


def build_macrochef_graph():
    """Uncheckpointed compiled graph -- used by the EXISTING
    `POST /recipes/recommend` and `/recipes/recommend/stream` endpoints via
    `run_recommendation_graph` below. Behavior is unchanged from before
    ROADMAP 3.2: no checkpointer, no `thread_id` needed to invoke, every
    image/mixed request auto-confirms low-confidence inventory exactly as
    today, since `MacroChefState.hitl_enabled` defaults False and these
    call sites never set it (see that field's docstring).

    Deliberately NOT `@lru_cache`d, unlike `get_compiled_macrochef_graph`
    below -- rebuilt fresh on every call, exactly as before ROADMAP 3.2.
    Caching it was tried and reverted: LangGraph's `add_node` captures node
    function references at COMPILE time, so a cached singleton would freeze
    in whatever `recipe_retriever_node` (etc.) resolved to at first build --
    breaking `tests/test_stream_endpoint.py::
    test_mid_graph_exception_yields_clean_error_event`'s monkeypatch of
    `builder_module.recipe_retriever_node` (which relies on a fresh compile
    picking up the patched reference), and, more importantly, the exact
    "old endpoints provably unchanged" invariant this step depends on. No
    checkpointer means no DB connection to protect, so per-request
    rebuilding is just as safe as it always was -- there was no real
    performance problem to fix here in the first place.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return SequentialMacroChefGraph()

    graph = _wire_graph(StateGraph(MacroChefState), START, END)
    return graph.compile()


def get_compiled_macrochef_graph():
    """Checkpointed graph -- used by `app.api.routes_runs` and
    `app.api.routes_stream`'s HITL branch (ROADMAP.md Phase 3, Step 3.2's
    true HITL entrypoints; the latter closes ROADMAP.md:146's requirement
    that the streaming endpoint itself can pause).

    Deliberately NOT `@lru_cache`d itself -- same reasoning as
    `build_macrochef_graph`'s docstring: LangGraph's `add_node` captures
    node function references at COMPILE time, so caching the compiled
    graph object would freeze in whatever `recipe_retriever_node` (etc.)
    resolved to at first build, breaking the same node-monkeypatch
    technique `test_stream_endpoint.py` relies on -- confirmed directly by
    building this step (caching this function initially reintroduced the
    exact regression `build_macrochef_graph` had already been reverted
    for). The actual expensive, connection-holding resource --
    `_get_checkpointer()` above -- IS cached separately, so this function
    is cheap to call on every request: it only re-wires nodes/edges
    (no I/O) and reuses the already-open checkpointer connection.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return SequentialMacroChefGraph()

    graph = _wire_graph(StateGraph(MacroChefState), START, END)
    return graph.compile(checkpointer=_get_checkpointer())


def request_to_state(
    request: RecommendationRequest, user_id: str, *, hitl_enabled: bool = False
) -> MacroChefState:
    # `user_id` always comes from the verified session token (see
    # app.dependencies.get_session_user, via
    # app.api.routes_recommendations.recommend_recipes), never from
    # `request` -- the wire schema has no user_id field to begin with. This
    # mirrors app.graph.library_builder.discovery_request_to_state.
    #
    # `hitl_enabled` (ROADMAP 3.2): keyword-only, defaults False, and NEVER
    # read from `request` -- there is no such field on RecommendationRequest
    # and there must never be one (see MacroChefState.hitl_enabled's
    # docstring: a client-settable flag here would let a caller opt itself
    # into a safety-adjacent pause path). Only app.api.routes_runs.
    # invoke_hitl_graph (shared by that router's start_run and
    # app.api.routes_stream's HITL branch) passes `hitl_enabled=True`
    # explicitly, in code. recommend_recipes (POST /recommend) and the
    # non-interrupting branch of POST /recommend/stream omit it and get
    # False, unchanged.
    return MacroChefState(
        user_id=user_id,
        hitl_enabled=hitl_enabled,
        input_type=request.input_type,
        image_path=request.image_path,
        typed_ingredients=request.typed_ingredients,
        user_profile=request.user_profile,
        confirmed_inventory=request.confirmed_inventory or [],
        cuisine_preference=request.cuisine_preference,
        meal_type=request.meal_type,
    )


def build_recommendation_response(final_state: MacroChefState) -> RecommendationResponse:
    """Shared `MacroChefState -> RecommendationResponse` mapping -- used by
    `run_recommendation_graph` below (POST /recommend, and /recommend/stream's
    non-interrupting/fallback branches) and, since ROADMAP 3.2, by
    `app.api.routes_runs.status_from_invoke_result` for the "completed"
    branch of the checkpointed HITL flow (both `/runs` and the streaming
    HITL branch). Factored out so there is exactly one place this mapping
    is defined, not two copies that could drift."""
    return RecommendationResponse(
        recommendations=final_state.final_recommendations,
        shopping_list=final_state.shopping_list,
        rejected_recipes=final_state.rejected_recipes,
        inventory_observations=final_state.raw_inventory_observations,
        debug_trace=final_state.debug_trace,
        errors=final_state.errors,
        taste_profile=final_state.taste_profile,
        waste_nudges=final_state.waste_nudges,
    )


def run_recommendation_graph(request: RecommendationRequest, user_id: str) -> RecommendationResponse:
    # Bind user_id into the observability contextvar (ROADMAP 1.2) for the
    # duration of this graph run -- intake_node may call vision extraction
    # (app.services.vision_service -> model_provider._extract_inventory),
    # several call-frames below, and the LLM ledger needs user_id there
    # without threading it through every node's signature. See
    # app.observability.events.bind_user_id's docstring.
    user_id_token = bind_user_id(user_id)
    try:
        graph = build_macrochef_graph()
        state = request_to_state(request, user_id)
        result = graph.invoke(state.model_dump())
    finally:
        reset_user_id(user_id_token)
    final_state = ensure_state(result)
    response = build_recommendation_response(final_state)

    analytics = get_analytics()
    analytics.capture(
        user_id,
        "request completed",
        {"had_errors": bool(response.errors), "recommendation_count": len(response.recommendations)},
    )
    if response.recommendations:
        analytics.capture(
            user_id,
            "plan generated",
            {"recommendation_count": len(response.recommendations)},
        )
    return response
