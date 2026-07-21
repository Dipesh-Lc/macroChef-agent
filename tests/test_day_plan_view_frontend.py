"""C1: minimal day-plan "plan canvas" display -- pure-function tests for the
non-Streamlit-widget helpers in `components.day_plan_view`. Full
`render_day_plan` is a thin `st.*` composition over these and over
`app.schemas.day_plan.DayPlan` fields already covered by
`tests/test_day_planner.py` / `tests/test_routes_day_planner.py`; this file
only covers the display-layer arithmetic/escaping that is new here.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.day_plan_view import _plan_item_lines, _progress_ratio  # noqa: E402

MALICIOUS_TITLE = "<script>alert(1)</script>"


def test_progress_ratio_normal_case() -> None:
    assert _progress_ratio(1000.0, 2000.0) == 0.5


def test_progress_ratio_clamps_above_target_to_one() -> None:
    assert _progress_ratio(3000.0, 2000.0) == 1.0


def test_progress_ratio_zero_target_returns_zero_not_a_crash() -> None:
    assert _progress_ratio(500.0, 0.0) == 0.0


def test_progress_ratio_negative_target_returns_zero() -> None:
    assert _progress_ratio(500.0, -10.0) == 0.0


def test_plan_item_lines_include_title_and_servings() -> None:
    lines = _plan_item_lines([{"title": "Chicken Rice Bowl", "servings": 2}])

    assert "Chicken Rice Bowl" in lines
    assert "2x serving(s)" in lines


def test_plan_item_lines_escape_recipe_title() -> None:
    lines = _plan_item_lines([{"title": MALICIOUS_TITLE, "servings": 1}])

    assert "<script>alert(1)</script>" not in lines
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in lines
