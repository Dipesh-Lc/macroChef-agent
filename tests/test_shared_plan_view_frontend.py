"""Roadmap item "Shareable plan URLs" (Phase 4 item 4) -- frontend test for
the pure markup-building function in `components.shared_plan_view`, the
read-only recipe view rendered by `frontend/pages/2_Shared_Plan.py` for a
`plan_type == "recipe"` share link.

Mirrors the escaping-discipline tests already used for every other
recipe/import-derived text sink in this package (see
`tests/test_waste_nudge_frontend.py`, `tests/test_day_plan_view_frontend.py`
-- `html_safe.escape_value` is the one chokepoint, exercised here through
the real production function, not a reimplementation).
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.shared_plan_view import public_recipe_markup  # noqa: E402

MALICIOUS_TITLE = "<script>alert('title')</script>"
MALICIOUS_DESCRIPTION = "<img src=x onerror=alert('desc')>"
MALICIOUS_INGREDIENT_NAME = "<script>alert('ingredient')</script>"
MALICIOUS_INSTRUCTION = "<script>alert('instruction')</script>"
MALICIOUS_ALLERGEN = "<script>alert('allergen')</script>"
MALICIOUS_DIET_TAG = "<script>alert('diet')</script>"


def _recipe(**overrides: object) -> dict:
    base: dict = {
        "recipe_id": "shared_recipe_1",
        "title": "Chicken Rice Bowl",
        "cuisine": "asian",
        "meal_type": "dinner",
        "cook_time_min": 25,
        "description": "A quick weeknight bowl.",
        "ingredients": [{"name": "chicken breast", "amount": 200, "unit": "g"}],
        "instructions": ["Cook the chicken.", "Cook the rice."],
        "allergens": ["gluten"],
        "diet_tags": ["high-protein"],
    }
    base.update(overrides)
    return base


def test_includes_title_meta_and_description() -> None:
    markup = public_recipe_markup(_recipe())
    assert "Chicken Rice Bowl" in markup
    assert "asian" in markup
    assert "dinner" in markup
    assert "25 min" in markup
    assert "A quick weeknight bowl." in markup


def test_includes_ingredient_and_instruction_lines() -> None:
    markup = public_recipe_markup(_recipe())
    assert "chicken breast" in markup
    assert "Cook the chicken." in markup
    assert "Cook the rice." in markup


def test_includes_allergen_and_diet_tags() -> None:
    markup = public_recipe_markup(_recipe())
    assert "gluten" in markup
    assert "high-protein" in markup


def test_missing_ingredients_shows_fallback_line() -> None:
    markup = public_recipe_markup(_recipe(ingredients=[]))
    assert "No structured ingredient amounts recorded." in markup


def test_missing_instructions_shows_fallback_line() -> None:
    markup = public_recipe_markup(_recipe(instructions=[]))
    assert "No instructions recorded." in markup


def test_title_is_escaped() -> None:
    markup = public_recipe_markup(_recipe(title=MALICIOUS_TITLE))
    assert "<script>alert('title')</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_description_is_escaped() -> None:
    markup = public_recipe_markup(_recipe(description=MALICIOUS_DESCRIPTION))
    assert "<img src=x onerror=alert" not in markup
    assert "&lt;img" in markup


def test_ingredient_name_is_escaped() -> None:
    markup = public_recipe_markup(
        _recipe(ingredients=[{"name": MALICIOUS_INGREDIENT_NAME, "amount": 1, "unit": "unit"}])
    )
    assert "<script>alert('ingredient')</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_instruction_step_is_escaped() -> None:
    markup = public_recipe_markup(_recipe(instructions=[MALICIOUS_INSTRUCTION]))
    assert "<script>alert('instruction')</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_allergen_tag_is_escaped() -> None:
    markup = public_recipe_markup(_recipe(allergens=[MALICIOUS_ALLERGEN]))
    assert "<script>alert('allergen')</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_diet_tag_is_escaped() -> None:
    markup = public_recipe_markup(_recipe(diet_tags=[MALICIOUS_DIET_TAG]))
    assert "<script>alert('diet')</script>" not in markup
    assert "&lt;script&gt;" in markup
