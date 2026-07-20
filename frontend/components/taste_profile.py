import streamlit as st

from html_safe import tag_row_html


def taste_profile_markup(taste_profile: dict | None) -> str:
    """Deterministic, templated markup for the derived taste-profile signal
    (Phase 3: visible personalization loop).

    Built ONLY from `TasteProfile.avoided_ingredients`/`preferred_cuisines`
    (app.services.memory_service.derive_taste_profile) -- no LLM-authored
    copy, the same "deterministic code decides, LLM never does" rule that
    governs allergy/nutrition decisions elsewhere in this repo. Reuses the
    existing tag-label/tag-row/used-tag/missing-tag CSS classes from
    `recommendation_cards.py` rather than inventing new ones.

    Returns "" when there is nothing to show. `derive_taste_profile` enforces
    a minimum-sample-size floor before either list is ever populated, so an
    empty response here always means "not enough feedback yet", never "a
    profile fabricated from one data point".
    """
    if not taste_profile:
        return ""
    avoided = taste_profile.get("avoided_ingredients") or []
    preferred = taste_profile.get("preferred_cuisines") or []
    if not avoided and not preferred:
        return ""

    sections = []
    if preferred:
        sections.append(
            '<div class="tag-label">Drifting toward these cuisines, based on what you\'ve liked</div>'
            f'<div class="tag-row">{tag_row_html(preferred, "used-tag")}</div>'
        )
    if avoided:
        sections.append(
            '<div class="tag-label">Auto-avoided ingredients, based on what you\'ve disliked</div>'
            f'<div class="tag-row">{tag_row_html(avoided, "missing-tag")}</div>'
        )
    return "".join(sections)


def render_taste_profile(taste_profile: dict | None) -> None:
    markup = taste_profile_markup(taste_profile)
    if not markup:
        return
    st.markdown('<div class="results-title">Your taste profile</div>', unsafe_allow_html=True)
    st.html(f'<div class="recipe-card">{markup}</div>')
