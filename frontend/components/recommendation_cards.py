from html import escape
from urllib.parse import quote_plus

import streamlit as st
from html_safe import escape_value

from app.schemas.ingredient import scale_ingredients
from app.schemas.recipe import Recipe
from app.services.nutrition_view import macro_display_state
from session_client import request_with_session


def _macro_badge(recipe: dict) -> str:
    # Reads the same `macro_display_state` the scorer uses (app.services.
    # nutrition_view) so the badge can never show a number the scorer didn't
    # also trust, and never falls back to a bare 0 for an ungrounded recipe.
    parsed = Recipe.model_validate(recipe)
    state = macro_display_state(parsed)
    if state == "unknown":
        return "Macros unknown"

    macros = parsed.nutrition.per_serving
    base = f"{macros.calories:.0f} kcal | {macros.protein_g:.0f}P / {macros.carbs_g:.0f}C / {macros.fat_g:.0f}F"
    if state == "partial":
        pct = round(parsed.nutrition.coverage * 100)
        base = f"~{base} (partial, {pct}% grounded, likely undercounts)"

    # B1: explicit N-of-M grounding count, shown alongside the kcal/P/C/F
    # line for GROUNDED and PARTIAL alike. Purely a count over `contributions
    # [*].grounded` -- display-only, never recomputed here, and never fed
    # back into `macro_display_state`/the scorer.
    contributions = parsed.nutrition.contributions
    if contributions:
        matched = sum(1 for item in contributions if item.grounded)
        base = f"{base} | {matched}/{len(contributions)} ingredients USDA-matched"
    return base


def _ingredient_amount_lines(parsed: Recipe, factor: float) -> str:
    # B2 serving scaler: render every ingredient's amount scaled by `factor`
    # via the pure `scale_ingredients` helper. Never fabricates an amount for
    # an ingredient whose original `amount` is None -- `scale_ingredients`
    # leaves those as None and `Ingredient.display()` falls back to the bare
    # name, so an unquantified ingredient stays honestly unquantified at any
    # serving count.
    scaled = scale_ingredients(parsed.ingredients, factor)
    if not scaled:
        return '<div class="ingredient-line">No structured ingredient amounts recorded.</div>'
    return "".join(
        f'<div class="ingredient-line">{escape_value(item.display())}</div>' for item in scaled
    )


def _batch_totals_line(parsed: Recipe, target_servings: int) -> str:
    # Batch macro total for the chosen serving count. Per-serving macros are
    # already serving-invariant, so this is the trivial `per_serving *
    # target_servings` described in the B2 spec -- no new nutrition
    # computation, no USDA lookup. Reuses the same `macro_display_state`
    # chokepoint as `_macro_badge` so a batch total is never shown for an
    # "unknown" recipe.
    state = macro_display_state(parsed)
    if state == "unknown":
        return ""
    macros = parsed.nutrition.per_serving
    kcal = macros.calories * target_servings
    protein = macros.protein_g * target_servings
    carbs = macros.carbs_g * target_servings
    fat = macros.fat_g * target_servings
    return (
        f"Batch total for {target_servings} serving(s): "
        f"{kcal:.0f} kcal | {protein:.0f}P / {carbs:.0f}C / {fat:.0f}F"
    )


def _restored_badge(recipe: dict) -> str:
    # Deterministic display-only flag set by app.rag.loaders.attach_restoration
    # from the A1 corpus-rebuild reimport ledger (recipe_id tagged
    # bucket == "released") -- never decided or worded by the LLM. Purely
    # informational: absent for every recipe that wasn't recovered from
    # quarantine, present (fixed copy, nothing recipe-derived interpolated)
    # for the ~981 that were. See roadmap item B6.
    if not recipe.get("restored_from_quarantine"):
        return ""
    return (
        '<span class="restored-badge" '
        'title="Recovered from an earlier import\'s quarantine after the '
        '2026-07-19 corpus rebuild verified it against the original recipe '
        'page.">Restored from source</span>'
    )


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
    # No user_id in the payload, deliberately -- identity for this request
    # is derived exclusively from the verified session token, sent via
    # `request_with_session` (see frontend.session_client and
    # app.schemas.recommendation.FeedbackRequest).
    payload = {
        "recipe_id": recipe_id,
        "feedback_type": feedback_type,
        "notes": "Submitted from Streamlit demo",
    }
    request_with_session(
        "POST", f"{api_url}/feedback", json=payload, timeout=15
    ).raise_for_status()
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
                      {_restored_badge(recipe)}
                    </div>
                    <div class="macro-badge">{escape(_macro_badge(recipe))}</div>
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

        # B2 serving scaler. Range is 1..max(8, recipe.servings) so a recipe
        # that naturally serves more than 8 (e.g. a party-size batch) is
        # still reachable at its own default rather than being clamped below
        # it -- a deliberate design call, not a spec requirement. Default is
        # the recipe's own serving count (or 1 if unset), matching what the
        # per-serving macros already assume. `key=` is per-recipe so each
        # card's slider is independent, matching the Like/Dislike/Cooked
        # button pattern below.
        parsed_recipe = Recipe.model_validate(recipe)
        default_servings = recipe.get("servings") or 1
        target_servings = st.slider(
            "Servings",
            min_value=1,
            max_value=max(8, default_servings),
            value=default_servings,
            key=f"servings_{recipe['recipe_id']}",
        )
        scale_factor = target_servings / default_servings

        with st.expander(f"Ingredients for {target_servings} serving(s)"):
            st.html(f'<div class="ingredient-list">{_ingredient_amount_lines(parsed_recipe, scale_factor)}</div>')
            batch_line = _batch_totals_line(parsed_recipe, target_servings)
            if batch_line:
                st.caption(batch_line)

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
