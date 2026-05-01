from app.graph.library_state import RecipeLibraryBuilderState, ensure_library_state


def after_library_step(state: RecipeLibraryBuilderState | dict) -> str:
    current = ensure_library_state(state)
    if current.errors:
        return "end"
    return "continue"
