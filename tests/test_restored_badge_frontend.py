"""B6: "Restored from source" badge -- frontend display-only marker.

Exercises the real production markup function
(`components.recommendation_cards._restored_badge`) rather than a
reimplementation, mirroring the pattern in `test_frontend_escaping.py`. The
underlying flag (`Recipe.restored_from_quarantine`) is set deterministically
at load time (`app.rag.loaders.attach_restoration`, covered by
`tests/test_loaders.py`) -- the LLM never sees or decides this value, and
this module only ever renders it, never computes it.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.recommendation_cards import _restored_badge  # noqa: E402


def test_restored_badge_shown_for_restored_recipe() -> None:
    html = _restored_badge({"recipe_id": "imp_1", "title": "T", "restored_from_quarantine": True})

    assert 'class="restored-badge"' in html
    assert "Restored from source" in html


def test_restored_badge_absent_for_normal_recipe() -> None:
    assert _restored_badge({"recipe_id": "imp_2", "title": "T", "restored_from_quarantine": False}) == ""


def test_restored_badge_absent_when_field_missing() -> None:
    # Recipes predating this field (or any dict missing the key) must default
    # to "no badge", never raise.
    assert _restored_badge({"recipe_id": "imp_3", "title": "T"}) == ""
