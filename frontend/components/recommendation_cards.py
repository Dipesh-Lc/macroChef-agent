from html import escape
from urllib.parse import quote_plus

import requests
import streamlit as st


def _score_tile(label: str, value: float) -> str:
    return f"""
    <div class="score-tile">
      <div class="score-value">{value:.0%}</div>
      <div class="score-label">{label}</div>
    </div>
    """


def _recipe_image_url(recipe: dict) -> str:
    title = quote_plus(recipe.get("title") or "MacroChef meal")
    cuisine = quote_plus(recipe.get("cuisine") or "meal")
    return f"https://placehold.co/520x360/243f36/bff4de/png?text={cuisine}+recipe%0A{title}"


def _tags(items: list[str], css_class: str) -> str:
    return "".join(f'<span class="{css_class}">{escape(str(item))}</span>' for item in items)


def _post_feedback(api_url: str, recipe_id: str, feedback_type: str) -> None:
    payload = {
        "user_id": "demo_user",
        "recipe_id": recipe_id,
        "feedback_type": feedback_type,
        "notes": "Submitted from Streamlit demo",
    }
    requests.post(f"{api_url}/feedback", json=payload, timeout=15).raise_for_status()
    st.toast(f"Saved: {feedback_type}")


def render_recommendations(api_url: str, recommendations: list[dict]) -> None:
    if not recommendations:
        return

    st.markdown('<div class="results-title">Top recipe matches</div>', unsafe_allow_html=True)
    for index, recommendation in enumerate(recommendations, start=1):
        recipe = recommendation["recipe"]
        score = recommendation["score"]
        used = score["used_ingredients"] or ["None"]
        missing = score["missing_ingredients"] or ["Nothing essential"]
        description = recipe.get("description") or "A practical meal match based on your pantry, nutrition targets, and hard safety constraints."
        image_url = _recipe_image_url(recipe)

        st.html(
            f"""
            <div class="recipe-card {'top-card' if index == 1 else ''}">
              <div class="recipe-card-layout">
                <img class="recipe-image" src="{image_url}" alt="{escape(recipe['title'])}">
                <div class="recipe-content">
                  <div class="recipe-card-header">
                    <div>
                      <div class="recipe-title">{index}. {escape(recipe['title'])}</div>
                      <div class="recipe-meta">
                        {escape(recipe.get('cuisine') or 'Any cuisine')} | {escape(recipe.get('meal_type') or 'meal')} | {recipe.get('cook_time_min') or '?'} min
                      </div>
                    </div>
                    <div class="macro-badge">{recipe.get('calories', 0):.0f} kcal | {recipe.get('protein_g', 0):.0f}P / {recipe.get('carbs_g', 0):.0f}C / {recipe.get('fat_g', 0):.0f}F</div>
                  </div>
                  <div class="score-grid">
                    {_score_tile('Final', score['final_score'])}
                    {_score_tile('Pantry', score['pantry_match_score'])}
                    {_score_tile('Macros', score['macro_fit_score'])}
                    {_score_tile('Time', score['time_score'])}
                  </div>
                  <div class="recipe-description">{escape(description)}</div>
                  <div class="explanation">{escape(recommendation['explanation'])}</div>
                  <div class="tag-label">Used ingredients</div>
                  <div class="tag-row">{_tags(used, 'used-tag')}</div>
                  <div class="tag-label">Missing ingredients</div>
                  <div class="tag-row">{_tags(missing, 'missing-tag')}</div>
                </div>
              </div>
            </div>
            """
        )

        with st.expander("Instructions"):
            for step_idx, step in enumerate(recipe["instructions"], start=1):
                st.write(f"{step_idx}. {step}")

        cols = st.columns(3)
        if cols[0].button("Like", key=f"like_{recipe['recipe_id']}", width="stretch"):
            _post_feedback(api_url, recipe["recipe_id"], "liked")
        if cols[1].button("Dislike", key=f"dislike_{recipe['recipe_id']}", width="stretch"):
            _post_feedback(api_url, recipe["recipe_id"], "disliked")
        if cols[2].button("Cooked this", key=f"cooked_{recipe['recipe_id']}", width="stretch"):
            _post_feedback(api_url, recipe["recipe_id"], "cooked")
