import streamlit as st

from html_safe import tag_row_html


def shopping_list_markup(shopping: list[dict]) -> str:
    """Build the shopping-list pill-row markup.

    Ingredient names here come from recipe data (LLM-generated recipe
    candidates or external-import recipes) -- attacker-influenceable, not
    self-input or a static literal. This is the exact sink an advisor
    security review flagged in `frontend/streamlit_app.py`; every name is
    escaped via `html_safe.tag_row_html` before reaching this
    unsafe_allow_html sink.
    """
    return tag_row_html([item["name"] for item in shopping], "missing-tag")


def render_shopping_list(shopping: list[dict]) -> None:
    if not shopping:
        return
    st.markdown('<div class="results-title">Shopping list</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="tag-row">{shopping_list_markup(shopping)}</div>',
        unsafe_allow_html=True,
    )
