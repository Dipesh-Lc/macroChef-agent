"""Phase 4 (expiry/waste tracking) -- frontend display-only marker.

Exercises the real production markup function
(`components.waste_nudge.waste_nudge_markup`) rather than a
reimplementation, mirroring the pattern in `test_taste_profile_frontend.py`
/ `test_safety_banner_frontend.py`. The underlying data
(`WasteNudge.ingredient_name`/`days_until_expiry`/`suggested_recipes`,
`app.schemas.waste_tracking.WasteNudge`) is computed deterministically by
`app.services.waste_tracking.build_waste_nudges` -- the LLM never sees or
decides this value, and this module only ever renders it, never computes
it.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.waste_nudge import waste_nudge_markup  # noqa: E402


def _nudge(
    ingredient_name: str,
    days_until_expiry: int | None = None,
    suggested_recipes: list[dict] | None = None,
) -> dict:
    return {
        "ingredient_name": ingredient_name,
        "days_until_expiry": days_until_expiry,
        "suggested_recipes": suggested_recipes or [],
    }


def test_empty_when_no_nudges() -> None:
    assert waste_nudge_markup([]) == ""


def test_shows_ingredient_name_and_recipe_titles() -> None:
    markup = waste_nudge_markup(
        [
            _nudge(
                "spinach",
                days_until_expiry=0,
                suggested_recipes=[
                    {"recipe_id": "r1", "title": "Spinach Frittata"},
                    {"recipe_id": "r2", "title": "Spinach Feta Pie"},
                ],
            )
        ]
    )

    assert "spinach" in markup
    assert "Spinach Frittata" in markup
    assert "Spinach Feta Pie" in markup


def test_today_phrasing_for_zero_or_missing_days() -> None:
    markup_zero = waste_nudge_markup([_nudge("spinach", days_until_expiry=0)])
    markup_none = waste_nudge_markup([_nudge("spinach", days_until_expiry=None)])
    markup_negative = waste_nudge_markup([_nudge("spinach", days_until_expiry=-2)])

    assert "today" in markup_zero
    assert "today" in markup_none
    assert "today" in markup_negative


def test_tomorrow_phrasing_for_one_day() -> None:
    markup = waste_nudge_markup([_nudge("spinach", days_until_expiry=1)])
    assert "tomorrow" in markup


def test_in_n_days_phrasing_for_multiple_days() -> None:
    markup = waste_nudge_markup([_nudge("spinach", days_until_expiry=3)])
    assert "in 3 days" in markup


def test_ways_count_reflects_number_of_suggested_recipes() -> None:
    markup_one = waste_nudge_markup(
        [_nudge("spinach", suggested_recipes=[{"recipe_id": "r1", "title": "Recipe One"}])]
    )
    markup_three = waste_nudge_markup(
        [
            _nudge(
                "spinach",
                suggested_recipes=[
                    {"recipe_id": "r1", "title": "Recipe One"},
                    {"recipe_id": "r2", "title": "Recipe Two"},
                    {"recipe_id": "r3", "title": "Recipe Three"},
                ],
            )
        ]
    )

    assert "1 way" in markup_one
    assert "1 ways" not in markup_one
    assert "3 ways" in markup_three


def test_no_suggested_recipes_omits_the_ways_count() -> None:
    markup = waste_nudge_markup([_nudge("spinach", suggested_recipes=[])])
    assert "way" not in markup
    assert "No recipe suggestions found" in markup


def test_multiple_nudges_all_render() -> None:
    markup = waste_nudge_markup([_nudge("spinach"), _nudge("basil")])
    assert "spinach" in markup
    assert "basil" in markup


def test_ingredient_and_recipe_names_are_escaped() -> None:
    markup = waste_nudge_markup(
        [
            _nudge(
                "<script>alert(1)</script>",
                suggested_recipes=[
                    {"recipe_id": "r1", "title": "<img src=x onerror=alert(1)>"}
                ],
            )
        ]
    )

    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
    assert "<img src=x" not in markup
    assert "&lt;img" in markup
