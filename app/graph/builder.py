from app.graph.edges import (
    after_fallback,
    after_intake,
    after_inventory_confirmation,
    after_safety_filter,
)
from app.graph.nodes import (
    chef_explanation_node,
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
)
from app.graph.state import MacroChefState, ensure_state
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


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

        for node in [
            nutrition_scoring_node,
            meal_ranking_node,
            chef_explanation_node,
            procurement_node,
            memory_update_node,
        ]:
            state = node(state)
        return state


def build_macrochef_graph():
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
    graph.add_node("nutrition_scoring_node", nutrition_scoring_node)
    graph.add_node("meal_ranking_node", meal_ranking_node)
    graph.add_node("chef_explanation_node", chef_explanation_node)
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
            "nutrition_scoring": "nutrition_scoring_node",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "fallback_relaxation_node",
        after_fallback,
        {"nutrition_scoring": "nutrition_scoring_node", "end": END},
    )
    graph.add_edge("nutrition_scoring_node", "meal_ranking_node")
    graph.add_edge("meal_ranking_node", "chef_explanation_node")
    graph.add_edge("chef_explanation_node", "procurement_node")
    graph.add_edge("procurement_node", "memory_update_node")
    graph.add_edge("memory_update_node", END)
    return graph.compile()


def request_to_state(request: RecommendationRequest) -> MacroChefState:
    return MacroChefState(
        user_id=request.user_id,
        input_type=request.input_type,
        image_path=request.image_path,
        typed_ingredients=request.typed_ingredients,
        user_profile=request.user_profile,
        confirmed_inventory=request.confirmed_inventory or [],
        cuisine_preference=request.cuisine_preference,
        meal_type=request.meal_type,
    )


def run_recommendation_graph(request: RecommendationRequest) -> RecommendationResponse:
    graph = build_macrochef_graph()
    state = request_to_state(request)
    result = graph.invoke(state.model_dump())
    final_state = ensure_state(result)
    return RecommendationResponse(
        recommendations=final_state.final_recommendations,
        shopping_list=final_state.shopping_list,
        rejected_recipes=final_state.rejected_recipes,
        inventory_observations=final_state.raw_inventory_observations,
        debug_trace=final_state.debug_trace,
        errors=final_state.errors,
    )
