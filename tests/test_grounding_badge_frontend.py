"""B1: grounding N/M badge -- frontend display-only marker.

Exercises the real production markup function
(`components.recommendation_cards._macro_badge`) rather than a
reimplementation, mirroring the pattern in `test_restored_badge_frontend.py`.
The underlying grounding counts (`RecipeNutrition.contributions[*].grounded`)
are computed deterministically by `app.services.grounding_job.run_grounding`
-- the LLM never sees or decides this value, and this module only ever
renders it, never computes it. The trust state driving whether a macro line
is shown at all still comes from `app.services.nutrition_view.
macro_display_state`, unchanged by this task.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.recommendation_cards import _macro_badge  # noqa: E402


def _contribution(name: str, grounded: bool) -> dict:
    return {"name": name, "grounded": grounded}


def _recipe(status: str, contributions: list[dict], *, flags: list[str] | None = None) -> dict:
    macros = {"calories": 500, "protein_g": 40, "carbs_g": 50, "fat_g": 15, "fiber_g": 8}
    return {
        "recipe_id": "r1",
        "title": "Test Recipe",
        "ingredients": [],
        "instructions": ["Cook."],
        "nutrition": {
            "status": status,
            "servings": 1,
            "total": macros,
            "per_serving": macros,
            "contributions": contributions,
            "coverage": 1.0 if status == "grounded" else 0.5,
            "flags": flags or [],
        },
    }


def test_grounded_badge_shows_n_of_m_matched() -> None:
    contributions = [
        _contribution("chicken", True),
        _contribution("rice", True),
        _contribution("broccoli", False),
    ]
    badge = _macro_badge(_recipe("grounded", contributions))

    assert "500 kcal" in badge
    assert "2/3 ingredients USDA-matched" in badge


def test_partial_badge_shows_n_of_m_matched_alongside_partial_wording() -> None:
    contributions = [
        _contribution("chicken", True),
        _contribution("rice", False),
    ]
    badge = _macro_badge(_recipe("partial", contributions))

    assert "partial" in badge
    assert "likely undercounts" in badge
    assert "1/2 ingredients USDA-matched" in badge


def test_unknown_state_has_no_grounding_count() -> None:
    # No `nutrition` at all -> macro_display_state is "unknown"; nothing to
    # count, and the badge must not crash or show a count.
    badge = _macro_badge({"recipe_id": "r2", "title": "T", "ingredients": [], "instructions": []})

    assert badge == "Macros unknown"
    assert "USDA-matched" not in badge


def test_ungrounded_status_has_no_grounding_count() -> None:
    contributions = [_contribution("chicken", False)]
    badge = _macro_badge(_recipe("ungrounded", contributions))

    assert badge == "Macros unknown"
    assert "USDA-matched" not in badge
