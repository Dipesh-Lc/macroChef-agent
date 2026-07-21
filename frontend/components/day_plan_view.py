"""C1: minimal "plan canvas" view for the day-plan backend shipped in
B3 (app.services.day_planner) / B4 (app.services.procurement_service), which
had no Streamlit UI yet. Pure display over an already-assembled
`app.schemas.day_plan.DayPlanResponse` -- `plan.items`/totals/targets were
already computed by `app.api.routes_day_planner.plan_day`, and every
candidate recipe was already safety-cleared there via
`constraint_engine.validate_recipe` before the planner ever saw it (see that
route's docstring). This module makes no new safety or nutrition decision;
`_progress_ratio` is plain arithmetic over already-computed totals/targets.

v1 scope, deliberately minimal per the task spec: recipe list + a
progress-bar-style "total vs target" display for calories/protein via
`st.progress` (a built-in Streamlit primitive -- no new charting
dependency). Deeper day-plan UI polish (shopping-list wiring, remaining-
macros mode, etc.) is left for a later item.
"""

from __future__ import annotations

import streamlit as st

from html_safe import escape_value


def _progress_ratio(total: float, target: float) -> float:
    """Clamp `total / target` into `st.progress`'s required [0.0, 1.0]
    domain. `target <= 0` (no target set, or a zero target) returns 0.0
    rather than raising `ZeroDivisionError` -- `st.progress` cannot express
    "no target", and 0.0 is the safer fallback (never renders a false 100%
    for an unset target)."""
    if target <= 0:
        return 0.0
    return max(0.0, min(1.0, total / target))


def _plan_item_lines(items: list[dict]) -> str:
    """HTML-escaped "<title> - Nx serving(s)" lines. `title` is recipe/
    import-derived (attacker-influenceable), so it is escaped exactly like
    the other recipe-title sinks in this package (`safety_banner.py`,
    `recommendation_cards.py`)."""
    lines = []
    for item in items:
        title = escape_value(item.get("title") or "Untitled recipe")
        servings = item.get("servings", 1)
        lines.append(f'<div class="ingredient-line">{title} - {servings}x serving(s)</div>')
    return "".join(lines)


def render_day_plan(day_plan_response: dict) -> None:
    plan = day_plan_response.get("plan") or {}
    items = plan.get("items") or []

    st.markdown('<div class="results-title">Day plan</div>', unsafe_allow_html=True)

    if not items:
        st.info(
            "No feasible day plan could be assembled from your currently "
            "safe, matching recipes."
        )
        return

    if plan.get("within_tolerance"):
        st.success(
            f"Assembled {plan.get('meals_planned', 0)} meal-serving(s) within "
            "your macro tolerance (+/-10% calories, +/-15% protein)."
        )
    else:
        st.warning(
            f"Assembled {plan.get('meals_planned', 0)} meal-serving(s) -- this "
            "is the CLOSEST plan found; it did not land within your +/-10% "
            "calorie / +/-15% protein tolerance."
        )

    calories = plan.get("total_calories", 0.0)
    target_calories = plan.get("target_calories", 0.0)
    protein = plan.get("total_protein_g", 0.0)
    target_protein = plan.get("target_protein_g", 0.0)

    st.caption(f"Calories: {calories:.0f} / {target_calories:.0f} target")
    st.progress(_progress_ratio(calories, target_calories))
    st.caption(f"Protein: {protein:.0f}g / {target_protein:.0f}g target")
    st.progress(_progress_ratio(protein, target_protein))

    st.html(f'<div class="ingredient-list">{_plan_item_lines(items)}</div>')
