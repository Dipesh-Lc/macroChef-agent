from app.graph.library_edges import after_library_step
from app.graph.library_nodes import (
    candidate_presentation_node,
    deduplication_node,
    discovery_node,
    index_recipe_node,
    normalization_node,
    recipe_validation_node,
    save_recipe_node,
    selected_candidate_validation_node,
)
from app.graph.library_state import RecipeLibraryBuilderState, ensure_library_state
from app.schemas.library import (
    RecipeDiscoveryRequest,
    RecipeDiscoveryResponse,
    SaveRecipeCandidatesRequest,
    SaveRecipeCandidatesResponse,
)


class SequentialLibraryDiscoveryGraph:
    def invoke(self, initial_state: dict) -> dict:
        state = discovery_node(initial_state)
        if after_library_step(state) == "end":
            return state
        for node in [
            normalization_node,
            recipe_validation_node,
            deduplication_node,
            candidate_presentation_node,
        ]:
            state = node(state)
            if after_library_step(state) == "end":
                return state
        return state


class SequentialLibrarySaveGraph:
    def invoke(self, initial_state: dict) -> dict:
        state = selected_candidate_validation_node(initial_state)
        if after_library_step(state) == "end":
            return state
        state = save_recipe_node(state)
        if after_library_step(state) == "end":
            return state
        return index_recipe_node(state)


def build_library_discovery_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return SequentialLibraryDiscoveryGraph()

    graph = StateGraph(RecipeLibraryBuilderState)
    graph.add_node("discovery_node", discovery_node)
    graph.add_node("normalization_node", normalization_node)
    graph.add_node("recipe_validation_node", recipe_validation_node)
    graph.add_node("deduplication_node", deduplication_node)
    graph.add_node("candidate_presentation_node", candidate_presentation_node)

    graph.add_edge(START, "discovery_node")
    graph.add_conditional_edges(
        "discovery_node",
        after_library_step,
        {"continue": "normalization_node", "end": END},
    )
    graph.add_edge("normalization_node", "recipe_validation_node")
    graph.add_edge("recipe_validation_node", "deduplication_node")
    graph.add_edge("deduplication_node", "candidate_presentation_node")
    graph.add_edge("candidate_presentation_node", END)
    return graph.compile()


def build_library_save_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return SequentialLibrarySaveGraph()

    graph = StateGraph(RecipeLibraryBuilderState)
    graph.add_node("selected_candidate_validation_node", selected_candidate_validation_node)
    graph.add_node("save_recipe_node", save_recipe_node)
    graph.add_node("index_recipe_node", index_recipe_node)
    graph.add_edge(START, "selected_candidate_validation_node")
    graph.add_edge("selected_candidate_validation_node", "save_recipe_node")
    graph.add_edge("save_recipe_node", "index_recipe_node")
    graph.add_edge("index_recipe_node", END)
    return graph.compile()


def discovery_request_to_state(request: RecipeDiscoveryRequest) -> RecipeLibraryBuilderState:
    return RecipeLibraryBuilderState(**request.model_dump())


def save_request_to_state(request: SaveRecipeCandidatesRequest) -> RecipeLibraryBuilderState:
    return RecipeLibraryBuilderState(
        user_id=request.user_id,
        selected_candidates=request.selected_candidates,
        count=len(request.selected_candidates),
    )


def run_library_discovery_graph(request: RecipeDiscoveryRequest) -> RecipeDiscoveryResponse:
    graph = build_library_discovery_graph()
    state = discovery_request_to_state(request)
    result = graph.invoke(state.model_dump())
    final_state = ensure_library_state(result)
    return RecipeDiscoveryResponse(
        candidates=final_state.validated_candidates,
        debug_trace=final_state.debug_trace,
        warnings=final_state.warnings,
        errors=final_state.errors,
    )


def run_library_save_graph(request: SaveRecipeCandidatesRequest) -> SaveRecipeCandidatesResponse:
    graph = build_library_save_graph()
    state = save_request_to_state(request)
    result = graph.invoke(state.model_dump())
    final_state = ensure_library_state(result)
    return SaveRecipeCandidatesResponse(
        saved_recipe_ids=final_state.saved_recipe_ids,
        skipped_duplicates=final_state.skipped_duplicates,
        failed_candidates=final_state.failed_candidates,
        debug_trace=final_state.debug_trace,
    )
