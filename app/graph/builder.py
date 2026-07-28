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


def build_macrochef_graph():
    # ROADMAP 3.1: narrowed from a bare `try: <entire build+compile> except
    # Exception: return SequentialMacroChefGraph()` to wrap ONLY the import,
    # matching app.graph.library_builder.build_library_discovery_graph's
    # existing pattern. The old broad `try` silently swallowed ANY error
    # during graph construction (a typo in an edge label, a node-signature
    # mismatch, a `StateGraph`/`graph.compile()` bug) with zero logging,
    # silently degrading every request to the untraced-by-LangGraph
    # sequential fallback runner -- exactly the kind of failure this same
    # streaming work needs to surface loudly, not hide. A missing/broken
    # `langgraph` import is the only case that should fall back quietly;
    # anything else in graph construction is a real bug that must raise.
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return SequentialMacroChefGraph()

    graph = StateGraph(MacroChefState)
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

    graph.add_edge(START, "intake_node")
    graph.add_conditional_edges(
        "intake_node",
        after_intake,
        {"inventory_confirmation": "inventory_confirmation_node", "end": END},
    )
    graph.add_conditional_edges(
        "inventory_confirmation_node",
        after_inventory_confirmation,
        {"constraint_builder": "constraint_builder_node", "end": END},
    )
    graph.add_edge("constraint_builder_node", "recipe_retriever_node")
    graph.add_edge("recipe_retriever_node", "safety_filter_node")
    graph.add_conditional_edges(
        "safety_filter_node",
        after_safety_filter,
        {
            "fallback_relaxation": "fallback_relaxation_node",
            "nutrition_scoring": "substitution_node",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "fallback_relaxation_node",
        after_fallback,
        {"nutrition_scoring": "substitution_node", "end": END},
    )
    graph.add_edge("substitution_node", "nutrition_scoring_node")
    graph.add_edge("nutrition_scoring_node", "meal_ranking_node")
    graph.add_edge("meal_ranking_node", "procurement_node")
    graph.add_edge("procurement_node", "memory_update_node")
    graph.add_edge("memory_update_node", END)
    return graph.compile()


def request_to_state(request: RecommendationRequest, user_id: str) -> MacroChefState:
    # `user_id` always comes from the verified session token (see
    # app.dependencies.get_session_user, via
    # app.api.routes_recommendations.recommend_recipes), never from
    # `request` -- the wire schema has no user_id field to begin with. This
    # mirrors app.graph.library_builder.discovery_request_to_state.
    return MacroChefState(
        user_id=user_id,
        input_type=request.input_type,
        image_path=request.image_path,
        typed_ingredients=request.typed_ingredients,
        user_profile=request.user_profile,
        confirmed_inventory=request.confirmed_inventory or [],
        cuisine_preference=request.cuisine_preference,
        meal_type=request.meal_type,
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
    response = RecommendationResponse(
        recommendations=final_state.final_recommendations,
        shopping_list=final_state.shopping_list,
        rejected_recipes=final_state.rejected_recipes,
        inventory_observations=final_state.raw_inventory_observations,
        debug_trace=final_state.debug_trace,
        errors=final_state.errors,
        taste_profile=final_state.taste_profile,
        waste_nudges=final_state.waste_nudges,
    )

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
