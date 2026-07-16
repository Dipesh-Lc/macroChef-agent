"""XSS-escaping regression tests for frontend unsafe_allow_html sinks.

An advisor security review found that `frontend/streamlit_app.py`'s
shopping-list rendering interpolated ingredient names -- which originate
from recipe data (LLM-generated or import-derived, i.e. attacker-influenceable)
-- into an `unsafe_allow_html=True` markdown block without escaping. A
crafted ingredient name could inject a `<script>` tag that reads the
non-HttpOnly session cookie (see `frontend/session_client.py` for why the
cookie can't be HttpOnly).

These tests exercise the actual production code paths (not a
reimplementation of `html.escape`) by importing the pure markup-building
functions the real sinks route values through:
`components.shopping_list.shopping_list_markup` (the exact function
`streamlit_app.py`'s shopping-list sink calls) and
`components.profile_form._tag_row_markup` (used by the profile
allergy/dislike tag sink). Both were confirmed to FAIL against the
pre-fix, unescaped versions of these functions before the escaping fix
was applied -- see the task report.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.profile_form import _tag_row_markup  # noqa: E402
from components.shopping_list import shopping_list_markup  # noqa: E402
from html_safe import escape_value, tag_row_html  # noqa: E402

MALICIOUS_NAME = "<script>alert(1)</script>"
MALICIOUS_ATTR_BREAKOUT = '"><img src=x onerror=alert(1)>'


def test_escape_value_neutralizes_script_tag():
    rendered = escape_value(MALICIOUS_NAME)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_escape_value_neutralizes_attribute_breakout():
    rendered = escape_value(MALICIOUS_ATTR_BREAKOUT)
    assert "<img" not in rendered
    assert '"' not in rendered.replace("&quot;", "")


def test_tag_row_html_escapes_each_item():
    html = tag_row_html([MALICIOUS_NAME, "flour"], "missing-tag")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert '<span class="missing-tag">flour</span>' in html


def test_shopping_list_markup_escapes_malicious_ingredient_name():
    """Proves the real shopping-list sink (`components/shopping_list.py`,
    called by `streamlit_app.py`) escapes a malicious recipe/LLM-derived
    ingredient name rather than rendering it as live markup.

    Confirmed to FAIL against the pre-fix version of `shopping_list_markup`
    (which interpolated `item["name"]` unescaped) before the fix was
    applied.
    """
    shopping = [{"name": MALICIOUS_NAME}, {"name": "flour"}]
    html = shopping_list_markup(shopping)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_profile_tag_row_escapes_malicious_self_input():
    """Profile allergy/dislike tags are self-input (never round-tripped
    through server storage back into this sink), but per the audit we
    escape them too, defense in depth.

    Confirmed to FAIL against the pre-fix version of `_tag_row_markup`
    (which interpolated `item` unescaped) before the fix was applied.
    """
    html = _tag_row_markup([MALICIOUS_NAME], "profile-tag")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
