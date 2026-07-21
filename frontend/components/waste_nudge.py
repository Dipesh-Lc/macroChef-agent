"""Phase 4: expiry / waste tracking -- deterministic, templated display.

Every string this module produces is a pure Python template built ONLY from
the structured `WasteNudge` list (`app.schemas.waste_tracking.WasteNudge` --
ingredient_name/days_until_expiry/suggested_recipes) that
`app.services.waste_tracking.build_waste_nudges` already computed
deterministically (see `app.graph.nodes.nutrition_scoring_node`). No
LLM-authored copy anywhere, mirroring the exact discipline already used by
`taste_profile_markup` (taste_profile.py) and `safety_banner_markup`
(safety_banner.py). `ingredient_name` and recipe `title` are recipe/
import-derived (attacker-influenceable, same trust class as the shopping-
list/recommendation-card sinks), so both are HTML-escaped via
`html_safe.escape_value` before reaching an `unsafe_allow_html`/`st.html`
sink.
"""

from __future__ import annotations

import streamlit as st

from html_safe import escape_value


def _timing_phrase(days_until_expiry: int | None) -> str:
    """"Today"/"tomorrow"/"in N days" -- matches the roadmap's own example
    phrasing ("use your spinach today"). `None` (no `purchase_date` logged
    to estimate from -- see `ConfirmedIngredient.days_until_expiry`) and any
    non-positive value are both treated as "today": both mean "don't wait".
    """
    if days_until_expiry is None or days_until_expiry <= 0:
        return "today"
    if days_until_expiry == 1:
        return "tomorrow"
    return f"in {days_until_expiry} days"


def _ways_phrase(recipe_count: int) -> str:
    if recipe_count == 0:
        return ""
    noun = "way" if recipe_count == 1 else "ways"
    return f" -- {recipe_count} {noun}"


def waste_nudge_markup(waste_nudges: list[dict]) -> str:
    """Build the "use your X today -- N ways" nudge panel markup.

    `waste_nudges` must be the structured list described in the module
    docstring -- never a string or an LLM response object. Returns "" when
    there is nothing to show (no expiring-soon inventory this request),
    exactly like `taste_profile_markup` does for "not enough feedback yet".
    """
    if not waste_nudges:
        return ""

    sections = []
    for nudge in waste_nudges:
        name = escape_value(nudge.get("ingredient_name") or "")
        if not name:
            continue
        timing = _timing_phrase(nudge.get("days_until_expiry"))
        suggested = nudge.get("suggested_recipes") or []
        ways = _ways_phrase(len(suggested))

        recipe_lines = "".join(
            f'<div class="ingredient-line">{escape_value(recipe.get("title") or "Untitled recipe")}</div>'
            for recipe in suggested
        )
        if not recipe_lines:
            recipe_lines = (
                '<div class="ingredient-line">No recipe suggestions found in the corpus yet.</div>'
            )

        sections.append(
            f'<div class="tag-label">Use your {name} {timing}{ways}</div>'
            f'<div class="ingredient-list">{recipe_lines}</div>'
        )
    return "".join(sections)


def render_waste_nudges(waste_nudges: list[dict] | None) -> None:
    markup = waste_nudge_markup(waste_nudges or [])
    if not markup:
        return
    st.markdown('<div class="results-title">Use it before it goes to waste</div>', unsafe_allow_html=True)
    st.html(f'<div class="recipe-card">{markup}</div>')
