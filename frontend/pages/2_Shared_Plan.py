"""Roadmap item "Shareable plan URLs" (Phase 4 item 4) -- read-only viewer
for a public share link (`GET /share/{id}`, `app/api/routes_share.py`).

Deliberately UNAUTHENTICATED: this page never sends the session token via
`request_with_session` (frontend/session_client.py) -- it calls the API with
a plain `requests.get` instead, matching the backend route's own design
(see `app.api.routes_share.get_share_view`'s docstring: GET /share/{id} is
unauthenticated by design, since anyone holding a share id -- not just the
original sharer -- must be able to open it).

Only `recipe` and `day` plan types have a frontend renderer anywhere in this
app today (`components.shared_plan_view.render_public_recipe` and
`components.day_plan_view.render_day_plan` respectively) -- `batch`/`week`
share links have no viewer here yet (out of scope for this task per its
spec) and fall through to an explicit "not viewable yet" message instead of
crashing.
"""

import os
import sys
from pathlib import Path

import requests
import streamlit as st

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.day_plan_view import render_day_plan  # noqa: E402
from components.shared_plan_view import render_public_recipe  # noqa: E402

API_URL = os.getenv("MACROCHEF_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Shared Plan", page_icon="MC", layout="wide")

st.title("Shared plan")

# Streamlit's supported query-param API (st.query_params, stable since
# 1.30 -- this repo pins streamlit>=1.57.0, see requirements.txt).
share_id = st.query_params.get("share_id")

if not share_id:
    st.info("Paste a share link (with ?share_id=... in the address bar) to view it here.")
else:
    try:
        response = requests.get(f"{API_URL}/share/{share_id}", timeout=30)
    except requests.RequestException as exc:
        st.error(f"Could not reach MacroChef API at {API_URL}: {exc}")
    else:
        if response.status_code == 404:
            st.error("This share link doesn't exist or was removed.")
        elif not response.ok:
            st.error(f"Could not load this share link ({response.status_code}).")
        else:
            body = response.json()
            # Non-optional by design (app.schemas.share.SharedPlanView) --
            # always shown prominently, never omitted.
            st.warning(body.get("disclaimer") or "")

            plan_type = body.get("plan_type")
            content = body.get("content") or {}

            if plan_type == "recipe":
                render_public_recipe(content)
            elif plan_type == "day":
                # render_day_plan expects the same {"plan": ...} wrapper
                # shape as app.schemas.day_plan.DayPlanResponse (see
                # frontend/streamlit_app.py's own call site) -- the shared
                # PublicDayPlan `content` IS that inner plan object, so it's
                # wrapped here to match without changing render_day_plan.
                render_day_plan({"plan": content})
            else:
                st.info(
                    f"This share link is a {plan_type or 'unknown'!r} plan, "
                    "which this app doesn't have a viewer for yet."
                )
