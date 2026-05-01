from app.graph.state import MacroChefState, ensure_state


def after_intake(state: MacroChefState | dict) -> str:
    current = ensure_state(state)
    if current.errors:
        return "end"
    return "inventory_confirmation"


def after_inventory_confirmation(state: MacroChefState | dict) -> str:
    current = ensure_state(state)
    if current.errors:
        return "end"
    return "constraint_builder"


def after_safety_filter(state: MacroChefState | dict) -> str:
    current = ensure_state(state)
    if current.errors:
        return "end"
    if len(current.candidate_recipes) < 3:
        return "fallback_relaxation"
    return "nutrition_scoring"


def after_fallback(state: MacroChefState | dict) -> str:
    current = ensure_state(state)
    if current.errors or not current.candidate_recipes:
        return "end"
    return "nutrition_scoring"
