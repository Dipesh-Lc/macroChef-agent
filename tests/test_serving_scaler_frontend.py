"""B2: serving scaler -- frontend display-only markup functions.

Exercises the real production markup functions
(`components.recommendation_cards._ingredient_amount_lines` and
`_batch_totals_line`) rather than reimplementations, mirroring the pattern in
`test_restored_badge_frontend.py` / `test_grounding_badge_frontend.py`. The
scaling itself is delegated to `app.schemas.ingredient.scale_ingredients`
(covered by `tests/test_serving_scaler.py`); these tests only check the
markup built around it, including the malicious-name escaping regression
covered elsewhere for other sinks (`tests/test_frontend_escaping.py`).
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.recommendation_cards import (  # noqa: E402
    _batch_totals_line,
    _ingredient_amount_lines,
)

from app.schemas.recipe import Recipe  # noqa: E402


def _recipe(ingredients: list[dict], nutrition: dict | None = None) -> Recipe:
    return Recipe.model_validate(
        {
            "recipe_id": "r1",
            "title": "Test Recipe",
            "ingredients": ingredients,
            "instructions": ["Cook."],
            "nutrition": nutrition,
        }
    )


def test_ingredient_lines_scale_amounts() -> None:
    recipe = _recipe([{"name": "rice", "amount": 100, "unit": "g"}])
    html = _ingredient_amount_lines(recipe, 2.0)

    assert "200 g rice" in html


def test_ingredient_lines_never_fabricate_missing_amount() -> None:
    recipe = _recipe([{"name": "salt to taste", "amount": None, "unit": None}])
    html = _ingredient_amount_lines(recipe, 3.0)

    assert "salt to taste" in html
    assert "None" not in html


def test_ingredient_lines_escape_malicious_name() -> None:
    recipe = _recipe([{"name": "<script>alert(1)</script>", "amount": 1, "unit": "g"}])
    html = _ingredient_amount_lines(recipe, 1.0)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_ingredient_lines_empty_recipe_has_placeholder_not_crash() -> None:
    recipe = _recipe([])
    html = _ingredient_amount_lines(recipe, 1.0)

    assert "No structured ingredient amounts recorded." in html


def test_batch_totals_multiplies_per_serving_by_target_servings() -> None:
    macros = {"calories": 500, "protein_g": 40, "carbs_g": 50, "fat_g": 15, "fiber_g": 8}
    recipe = _recipe(
        [{"name": "chicken", "amount": 150, "unit": "g"}],
        nutrition={
            "status": "grounded",
            "servings": 1,
            "total": macros,
            "per_serving": macros,
            "contributions": [{"name": "chicken", "grounded": True}],
            "coverage": 1.0,
            "flags": [],
        },
    )
    line = _batch_totals_line(recipe, 4)

    assert "4 serving(s)" in line
    assert "2000 kcal" in line  # 500 * 4
    assert "160P" in line  # 40 * 4


def test_batch_totals_hidden_when_macros_unknown() -> None:
    recipe = _recipe([{"name": "chicken", "amount": 150, "unit": "g"}], nutrition=None)

    assert _batch_totals_line(recipe, 4) == ""
