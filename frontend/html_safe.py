"""Escaping helpers for values interpolated into raw HTML sinks.

Any `st.markdown(..., unsafe_allow_html=True)` / `st.html(...)` call that
interpolates a recipe-derived, LLM-derived, import-derived, or user-entered
string is a live XSS sink unless that value is escaped first -- a crafted
ingredient/recipe name becomes a live `<script>` tag in the rendered page
otherwise (see the advisor security review that flagged
`streamlit_app.py`'s shopping-list rendering).

Every such sink should route its interpolated value(s) through
`escape_value` (or `tag_row_html` for the common "row of pill tags"
pattern) rather than reinventing `html.escape` calls inline, so the rule
lives in one place.
"""

from __future__ import annotations

from html import escape


def escape_value(value: object) -> str:
    """HTML-escape any value before it reaches an unsafe_allow_html sink."""
    return escape(str(value))


def tag_row_html(items: list, css_class: str) -> str:
    """Build a row of `<span class="...">value</span>` pills, escaping each item.

    Used for shopping-list items, profile allergy/dislike tags, and
    used/missing ingredient tags -- anywhere a list of short strings gets
    rendered as pills inside an unsafe_allow_html block.
    """
    return "".join(f'<span class="{css_class}">{escape_value(item)}</span>' for item in items)
