"""Roadmap item "Shareable plan URLs" (Phase 4 item 4) -- frontend test for
the pure, non-Streamlit-widget helper in `components.share_button`.

`render_share_button` itself is a thin `st.*`/`requests` composition already
covered end-to-end by `tests/test_routes_share.py` (the real POST /share
endpoint it calls) -- this file only covers the display-layer URL
composition that is new here, mirroring the pattern in
`tests/test_day_plan_view_frontend.py` / `tests/test_waste_nudge_frontend.py`.
"""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.share_button import compose_share_url  # noqa: E402


def test_compose_share_url_basic() -> None:
    url = compose_share_url("http://localhost:8501", "abc123")
    assert url == "http://localhost:8501/Shared_Plan?share_id=abc123"


def test_compose_share_url_strips_trailing_slash_on_base() -> None:
    url = compose_share_url("https://macrochef.example.com/", "abc123")
    assert url == "https://macrochef.example.com/Shared_Plan?share_id=abc123"


def test_compose_share_url_url_encodes_share_id() -> None:
    url = compose_share_url("http://localhost:8501", "abc/123 xyz")
    assert "abc%2F123+xyz" in url
    assert " " not in url


def test_compose_share_url_never_hardcodes_a_hostname_of_its_own() -> None:
    # The share_id composition trusts ONLY the caller-supplied base URL --
    # it never falls back to a baked-in public hostname of its own (that
    # would defeat the point of MACROCHEF_PUBLIC_URL being configurable).
    url_a = compose_share_url("https://a.example.com", "same-id")
    url_b = compose_share_url("https://b.example.com", "same-id")
    assert url_a != url_b
    assert "a.example.com" in url_a
    assert "b.example.com" in url_b
