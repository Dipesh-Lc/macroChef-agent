import os
import sys
from pathlib import Path

import requests
import streamlit as st

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components.library_builder_form import render_library_builder_form  # noqa: E402
from components.recipe_candidate_cards import render_recipe_candidate_cards  # noqa: E402
from components.saved_recipe_library import render_saved_recipe_library  # noqa: E402

API_URL = os.getenv("MACROCHEF_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Recipe Library Builder", page_icon="MC", layout="wide")

st.markdown(
    """
    <style>
    .block-container { max-width: 1200px; padding-top: 1.4rem; }
    .results-title {
      font-size: 1.35rem;
      font-weight: 700;
      margin: 1rem 0 .8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Recipe Library Builder")
st.caption(
    "Discover home-cookable recipe candidates, review them, and save the useful ones "
    "into your personal MacroChef recipe library."
)

form_payload = render_library_builder_form()

if st.button("Discover recipes", type="primary", width="stretch"):
    try:
        response = requests.post(f"{API_URL}/library/discover", json=form_payload, timeout=90)
        response.raise_for_status()
        st.session_state["library_discovery_response"] = response.json()
    except requests.RequestException as exc:
        st.error(f"Could not discover recipes: {exc}")

discovery_response = st.session_state.get("library_discovery_response")
selected = []
if discovery_response:
    if discovery_response.get("errors"):
        st.error(" | ".join(discovery_response["errors"]))
    if discovery_response.get("warnings"):
        with st.expander("Discovery warnings"):
            for warning in discovery_response["warnings"]:
                st.write(warning)
    selected = render_recipe_candidate_cards(discovery_response.get("candidates", []))

    if st.button("Save selected recipes", width="stretch", disabled=not selected):
        payload = {
            "user_id": form_payload["user_id"],
            "selected_candidates": selected,
        }
        try:
            response = requests.post(f"{API_URL}/library/save", json=payload, timeout=90)
            response.raise_for_status()
            result = response.json()
            st.session_state["library_save_response"] = result
            st.session_state.pop("saved_library_response", None)
            if result.get("saved_recipe_ids"):
                st.success(f"Saved {len(result['saved_recipe_ids'])} recipes.")
            if result.get("skipped_duplicates"):
                st.warning("Skipped duplicates: " + ", ".join(result["skipped_duplicates"]))
            if result.get("failed_candidates"):
                st.error(f"{len(result['failed_candidates'])} candidates failed validation.")
        except requests.RequestException as exc:
            st.error(f"Could not save recipes: {exc}")

    with st.expander("Debug trace"):
        for step in discovery_response.get("debug_trace", []):
            st.write(step)
        save_response = st.session_state.get("library_save_response")
        if save_response:
            st.write("---")
            for step in save_response.get("debug_trace", []):
                st.write(step)

render_saved_recipe_library(API_URL, form_payload["user_id"])
