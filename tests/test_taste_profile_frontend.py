"""Phase 3: visible personalization loop -- frontend display-only marker.

Exercises the real production markup function
(`components.taste_profile.taste_profile_markup`) rather than a
reimplementation, mirroring the pattern in `test_restored_badge_frontend.py`
and `test_grounding_badge_frontend.py`. The underlying data
(`TasteProfile.avoided_ingredients`/`preferred_cuisines`) is computed
deterministically by `app.services.memory_service.derive_taste_profile` --
the LLM never sees or decides this value, and this module only ever renders
it, never computes it.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.taste_profile import taste_profile_markup  # noqa: E402


def test_shows_both_avoided_ingredients_and_preferred_cuisines() -> None:
    markup = taste_profile_markup(
        {"avoided_ingredients": ["cilantro"], "preferred_cuisines": ["Italian"]}
    )

    assert "cilantro" in markup
    assert "Italian" in markup
    assert 'class="missing-tag"' in markup
    assert 'class="used-tag"' in markup


def test_shows_only_avoided_ingredients_when_no_cuisine_drift() -> None:
    markup = taste_profile_markup({"avoided_ingredients": ["cilantro"], "preferred_cuisines": []})

    assert "cilantro" in markup
    assert 'class="used-tag"' not in markup


def test_shows_only_preferred_cuisines_when_no_avoided_ingredients() -> None:
    markup = taste_profile_markup({"avoided_ingredients": [], "preferred_cuisines": ["Thai"]})

    assert "Thai" in markup
    assert 'class="missing-tag"' not in markup


def test_empty_when_neither_list_has_a_signal() -> None:
    # Not enough feedback history yet -- derive_taste_profile enforces the
    # minimum-sample-size floor, so both lists being empty must render
    # nothing rather than an empty-looking panel.
    assert taste_profile_markup({"avoided_ingredients": [], "preferred_cuisines": []}) == ""


def test_empty_when_taste_profile_missing_entirely() -> None:
    assert taste_profile_markup(None) == ""
    assert taste_profile_markup({}) == ""


def test_ingredient_and_cuisine_names_are_escaped() -> None:
    markup = taste_profile_markup(
        {"avoided_ingredients": ['<script>alert(1)</script>'], "preferred_cuisines": []}
    )

    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
