"""C2: deterministic, always-visible display of the safety filter's actual
output for the current request ("make safety visible" -- roadmap Stage C).

Every string this module produces is a pure Python template built ONLY from
`rejected_recipes` (a list shaped like `app.schemas.recommendation.
RejectedRecipe` -- recipe_id/title/reason), which is itself already computed
deterministically by `app.services.constraint_engine.validate_recipe` before
this module ever sees it (see `app.graph.nodes.safety_filter_node` and
`app.api.routes_day_planner.plan_day`, the two producers of this exact
shape). This module makes NO safety decision of its own -- it only counts
and labels an already-computed, already-safe result -- and takes NO
LLM-authored input anywhere: no string parameter, no LLM response object,
only the structured list. This mirrors the exact discipline already used by
`_restored_badge`/`_macro_badge` (recommendation_cards.py) and
`taste_profile_markup` (taste_profile.py).

`_categorize_reason` parses the small, closed set of literal strings
`constraint_engine.validate_recipe` actually returns (verified against
`app/services/constraint_engine.py` lines ~1241-1250 on 2026-07-20):
  - "Contains a user allergen"
  - "Contains a disliked ingredient"
  - f"Violates diet type: {diet_type}"
  - "Exceeds maximum cooking time"
and the `RejectedRecipe`-construction fallback "Rejected by hard constraint"
used wherever `rejection_reason` is None (app.graph.nodes,
app.api.routes_day_planner).

FLAGGED DEVIATION from the roadmap's illustrative example ("...excluded for
tree nuts"): today's "Contains a user allergen" / "Contains a disliked
ingredient" reason strings do NOT carry which specific allergen or
ingredient matched -- only the diet-type reason names anything specific.
This module therefore reports "excluded for an allergy" rather than
fabricating a specific allergen name the underlying data doesn't contain.
Only `app.services.constraint_engine.validate_recipe` could add that
granularity, and it is out of scope for this task (FULL TREATMENT tier,
not touched here) -- see the task report.
"""

from __future__ import annotations

from collections import OrderedDict

import streamlit as st

from html_safe import escape_value

_ALLERGEN_REASON = "Contains a user allergen"
_DISLIKE_REASON = "Contains a disliked ingredient"
_DIET_PREFIX = "Violates diet type: "
_COOK_TIME_REASON = "Exceeds maximum cooking time"
_FALLBACK_REASON = "Rejected by hard constraint"


def _categorize_reason(reason: str) -> str:
    """Map one exact `RejectedRecipe.reason` string to a short display label.

    Purely a string match/parse over the closed vocabulary
    `constraint_engine.validate_recipe` emits (see module docstring) --
    never a fabrication. The final `else` branch never invents a label: it
    echoes the raw reason text back unchanged, so a reason string outside
    today's known set (e.g. from a future constraint_engine change) is still
    reported honestly instead of being silently miscategorized or dropped.
    """
    if reason == _ALLERGEN_REASON:
        return "an allergy"
    if reason == _DISLIKE_REASON:
        return "a disliked ingredient"
    if reason.startswith(_DIET_PREFIX):
        diet_type = reason[len(_DIET_PREFIX) :]
        return f"not being {diet_type}"
    if reason == _COOK_TIME_REASON:
        return "exceeding your time limit"
    return reason


def safety_banner_markup(rejected_recipes: list[dict]) -> str:
    """Build the always-visible "filtered deterministically" summary line.

    `rejected_recipes` must be the structured list described in the module
    docstring -- never a string or an LLM response object. Only nonzero
    categories are ever mentioned (a category with a zero count for this
    request simply never appears, since it is only added to `counts` when
    an actual rejected recipe carries that reason).

    When `rejected_recipes` is empty, returns an honest "0 recipes
    excluded" line rather than an empty string -- this is deliberate: it
    keeps the safety filter's having run visible even when it excluded
    nothing, matching the roadmap's "always on screen" requirement (see
    `render_safety_banner`, which always calls this with the real list).
    """
    total = len(rejected_recipes)
    if total == 0:
        return "Filtered deterministically: 0 recipes excluded by your allergy, diet, and time filters."

    counts: "OrderedDict[str, int]" = OrderedDict()
    for item in rejected_recipes:
        reason = item.get("reason") or _FALLBACK_REASON
        label = _categorize_reason(reason)
        counts[label] = counts.get(label, 0) + 1

    clauses = []
    for index, (label, count) in enumerate(counts.items()):
        escaped_label = escape_value(label)
        if index == 0:
            clauses.append(f"{count} recipes excluded for {escaped_label}")
        else:
            clauses.append(f"{count} excluded for {escaped_label}")
    return f"Filtered deterministically: {', '.join(clauses)}."


def excluded_recipe_lines(rejected_recipes: list[dict]) -> str:
    """Per-recipe detail lines ("<title> - excluded: <category>"), HTML-
    escaped, for the optional detail expander below the always-visible
    summary line. Same zero-LLM, read-only-display discipline as
    `safety_banner_markup` -- `title` is recipe/import-derived (attacker-
    influenceable, same trust class as the shopping-list/recommendation-card
    sinks), so it is escaped via `html_safe.escape_value` exactly like those.
    """
    lines = []
    for item in rejected_recipes:
        title = escape_value(item.get("title") or "Untitled recipe")
        reason = item.get("reason") or _FALLBACK_REASON
        label = escape_value(_categorize_reason(reason))
        lines.append(f'<div class="ingredient-line">{title} - excluded: {label}</div>')
    return "".join(lines)


def render_safety_banner(rejected_recipes: list[dict]) -> None:
    """Always-visible safety-filter status (not inside an expander), plus an
    optional expander with the per-recipe detail -- mirrors the
    "summary always visible, detail in an expander" pattern already used by
    the ingredients/instructions sections in `recommendation_cards.py`.
    """
    markup = safety_banner_markup(rejected_recipes)
    st.html(f'<div class="safety-banner">{markup}</div>')
    if rejected_recipes:
        with st.expander(f"See {len(rejected_recipes)} excluded recipe(s)"):
            st.html(f'<div class="ingredient-list">{excluded_recipe_lines(rejected_recipes)}</div>')
