"""Roadmap item "Shareable plan URLs" (Phase 4 item 4, docs/ROADMAP.md) --
frontend button that POSTs a recipe/day-plan payload the caller already has
in Streamlit session state to the authenticated `POST /share` endpoint
(`app/api/routes_share.py`) and shows the resulting public share URL back to
the user.

This module makes NO safety or field-selection decision -- it only forwards
whatever `Recipe`/`DayPlan` dict the caller already holds (already produced
by the deterministic constraint-filtered/safety-cleared backend flows) to
the server. The server-side field-level allowlist in
`app.services.share_service` is the sole authority on what actually gets
persisted/exposed (see that module's docstring: `owner_user_id` and every
other private field are stripped there, never here). This module is pure
display + a single POST call.

`MACROCHEF_PUBLIC_URL` is a frontend-only setting used ONLY to compose the
shareable URL string shown to the user -- it is NEVER sent to the backend.
`app.schemas.share.ShareCreateResponse` deliberately excludes any hostname
(see that schema's docstring): the backend never hardcodes a public
hostname, the frontend composes the full URL itself.
"""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import quote_plus

import requests
import streamlit as st

from session_client import request_with_session

PUBLIC_URL = os.getenv("MACROCHEF_PUBLIC_URL", "http://localhost:8501")

# Matches Streamlit's own multipage URL-slug convention (a page file's
# leading "<number>_" prefix is stripped from the URL path, the remainder is
# kept as-is) for frontend/pages/2_Shared_Plan.py.
_SHARED_PLAN_PAGE_SLUG = "Shared_Plan"

PlanType = Literal["recipe", "day"]

# Maps the frontend's plan_type literal to the matching field name on
# app.schemas.share.ShareCreateRequest -- kept in sync with that schema by
# hand (only two of its four fields are reachable from this frontend today;
# batch/weekly plans have no renderer anywhere in this app, out of scope).
_REQUEST_FIELD: dict[PlanType, str] = {"recipe": "recipe", "day": "day_plan"}


def compose_share_url(public_base_url: str, share_id: str) -> str:
    """Pure string composition -- no Streamlit/network calls, unit-testable
    directly. Builds the full public share URL from `public_base_url` (the
    frontend-only `MACROCHEF_PUBLIC_URL` setting) and a `share_id` returned
    by `POST /share`."""
    base = (public_base_url or "").rstrip("/")
    return f"{base}/{_SHARED_PLAN_PAGE_SLUG}?share_id={quote_plus(share_id)}"


def render_share_button(
    api_url: str,
    plan_type: PlanType,
    payload: dict,
    key: str,
    label: str = "Share",
) -> None:
    """Renders a share button; on click POSTs `payload` (a `Recipe` dict for
    `plan_type="recipe"`, or a `DayPlan` dict for `plan_type="day"`) to
    `POST {api_url}/share` via the authenticated `request_with_session`
    helper (same session-token pattern as `_post_feedback` in
    `components/recommendation_cards.py` -- `POST /share` requires a
    verified session, see `app.api.routes_share.create_share_link`).

    On success, shows the composed public share URL in a `st.text_input` for
    easy copying (persisted in `st.session_state` under `key` so it survives
    the next Streamlit rerun instead of disappearing once the button's own
    one-shot click state resets). On failure (non-2xx, including a 429 rate
    limit) shows `st.error` with the response detail if available.
    """
    result_key = f"_share_button_url::{key}"

    if st.button(label, key=key, width="stretch"):
        body = {"plan_type": plan_type, _REQUEST_FIELD[plan_type]: payload}
        try:
            response = request_with_session(
                "POST", f"{api_url}/share", json=body, timeout=30
            )
        except requests.RequestException as exc:
            st.session_state.pop(result_key, None)
            st.error(f"Could not reach MacroChef API to create a share link: {exc}")
        else:
            if response.status_code == 429:
                st.session_state.pop(result_key, None)
                st.error("You're sharing too quickly. Please wait a bit and try again.")
            elif not response.ok:
                st.session_state.pop(result_key, None)
                detail = None
                try:
                    detail = response.json().get("detail")
                except Exception:
                    pass
                st.error(
                    f"Could not create a share link ({response.status_code}): "
                    f"{detail or response.text}"
                )
            else:
                share_id = response.json()["share_id"]
                st.session_state[result_key] = compose_share_url(PUBLIC_URL, share_id)

    share_url = st.session_state.get(result_key)
    if share_url:
        st.text_input("Share link", value=share_url, key=f"{result_key}::input")
