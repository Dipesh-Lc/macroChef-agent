"""Roadmap item "Shareable plan URLs" (Phase 4 item 4) -- minimal read-only
recipe display for `GET /share/{id}` when `plan_type == "recipe"`
(`frontend/pages/2_Shared_Plan.py`). This is deliberately NOT the
interactive recommendation card (`components.recommendation_cards.
render_recommendations`): no Like/Dislike/Cooked buttons, no servings
slider, no feedback POST, no Share button -- an anonymous share-link viewer
has no session to attach any of that to. Just the recipe/ingredient/
instruction display.

`recipe` here is always the `content` field of a `SharedPlanView` whose
`plan_type == "recipe"` -- i.e. an already-allowlisted `PublicRecipe` dict
(`app.schemas.share.PublicRecipe`), never a raw client `Recipe`, and never
containing `owner_user_id` (see `app.services.share_service`'s docstring for
the allowlist that guarantees this). This module makes no further filtering
or safety decision -- it is pure display. Recipe-derived text is
HTML-escaped via `html_safe.escape_value`, the same discipline used by every
other component in this package (see e.g. `components/waste_nudge.py`,
`components/safety_banner.py`).
"""

from __future__ import annotations

import streamlit as st

from html_safe import escape_value

from app.schemas.ingredient import Ingredient


def _ingredient_lines(ingredients: list[dict]) -> str:
    if not ingredients:
        return '<div class="ingredient-line">No structured ingredient amounts recorded.</div>'
    lines = []
    for item in ingredients:
        parsed = Ingredient.model_validate(item)
        lines.append(f'<div class="ingredient-line">{escape_value(parsed.display())}</div>')
    return "".join(lines)


def _instruction_lines(instructions: list[str]) -> str:
    if not instructions:
        return '<div class="ingredient-line">No instructions recorded.</div>'
    return "".join(
        f'<div class="ingredient-line">{index}. {escape_value(step)}</div>'
        for index, step in enumerate(instructions, start=1)
    )


def _tags(items: list[str], css_class: str) -> str:
    return "".join(f'<span class="{css_class}">{escape_value(item)}</span>' for item in items)


def public_recipe_markup(recipe: dict) -> str:
    """Build the read-only recipe card markup for a shared `PublicRecipe`
    dict. Pure string building, no Streamlit calls -- unit-testable exactly
    like `components.waste_nudge.waste_nudge_markup`."""
    title = escape_value(recipe.get("title") or "Untitled recipe")
    cuisine = escape_value(recipe.get("cuisine") or "Any cuisine")
    meal_type = escape_value(recipe.get("meal_type") or "meal")
    cook_time = recipe.get("cook_time_min")
    cook_time_text = f"{cook_time} min" if cook_time is not None else "? min"
    description = recipe.get("description") or ""

    sections = [
        f'<div class="recipe-title">{title}</div>',
        f'<div class="recipe-meta">{cuisine} | {meal_type} | {cook_time_text}</div>',
    ]
    if description:
        sections.append(f'<div class="recipe-description">{escape_value(description)}</div>')

    sections.append('<div class="tag-label">Ingredients</div>')
    sections.append(
        f'<div class="ingredient-list">{_ingredient_lines(recipe.get("ingredients") or [])}</div>'
    )
    sections.append('<div class="tag-label">Instructions</div>')
    sections.append(
        f'<div class="ingredient-list">{_instruction_lines(recipe.get("instructions") or [])}</div>'
    )

    allergens = recipe.get("allergens") or []
    if allergens:
        sections.append('<div class="tag-label">Allergens</div>')
        sections.append(f'<div class="tag-row">{_tags(allergens, "missing-tag")}</div>')

    diet_tags = recipe.get("diet_tags") or []
    if diet_tags:
        sections.append('<div class="tag-label">Diet tags</div>')
        sections.append(f'<div class="tag-row">{_tags(diet_tags, "used-tag")}</div>')

    return f'<div class="recipe-card">{"".join(sections)}</div>'


def render_public_recipe(recipe: dict) -> None:
    st.html(public_recipe_markup(recipe))
