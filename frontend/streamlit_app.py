import os

import requests
import streamlit as st
from components.debug_panel import render_debug_panel
from components.inventory_input import render_inventory_input
from components.profile_form import render_profile_sidebar
from components.recommendation_cards import render_recommendations

API_URL = os.getenv("MACROCHEF_API_URL", "http://localhost:8000")

st.set_page_config(page_title="MacroChef Agent", page_icon="MC", layout="wide")

st.markdown(
    """
    <style>
    :root {
      --macro-bg: #282a27;
      --macro-panel: #212320;
      --macro-border: #56564f;
      --macro-border-strong: #6b6a62;
      --macro-text: #f2f0eb;
      --macro-muted: #b2afa8;
      --macro-dim: #98958d;
      --macro-green: #1d9e75;
      --macro-green-soft: #243f36;
      --macro-warning: #53452c;
    }
    .stApp, [data-testid="stAppViewContainer"] {
      background: var(--macro-bg);
      color: var(--macro-text);
    }
    header[data-testid="stHeader"], [data-testid="stHeader"] {
      display: none !important;
    }
    .block-container {
      max-width: 100%;
      padding: 0 2.4rem 3rem;
    }
    [data-testid="stSidebar"] {
      background: var(--macro-panel);
      border-right: 1px solid var(--macro-border);
      min-width: 370px;
      max-width: 370px;
    }
    [data-testid="stSidebar"] * { color: var(--macro-text); }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .65rem; }
    .sidebar-title {
      color: var(--macro-muted);
      font-size: 1.55rem;
      letter-spacing: .06em;
      text-transform: uppercase;
      margin: .35rem 0 1.35rem;
    }
    .section-label, .step-label {
      color: var(--macro-dim);
      font-size: 1rem;
      letter-spacing: .08em;
      text-transform: uppercase;
      margin-bottom: .55rem;
    }
    .spaced { margin-top: 1.7rem; }
    .tag-row {
      display: flex;
      flex-wrap: wrap;
      gap: .45rem;
      margin: .35rem 0 .5rem;
    }
    .profile-tag, .used-tag, .missing-tag {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: .18rem .62rem;
      font-size: .8rem;
      border: 1px solid var(--macro-border);
    }
    .profile-tag, .used-tag {
      background: var(--macro-green-soft);
      color: #bff4de;
      border-color: #2f725b;
    }
    .missing-tag {
      background: var(--macro-warning);
      color: #f3d49a;
      border-color: #7b653d;
    }
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    textarea,
    [data-testid="stTextArea"] textarea {
      background: #2b2d29 !important;
      color: var(--macro-text) !important;
      border: 1px solid var(--macro-border) !important;
      border-radius: 10px !important;
    }
    [data-testid="stTextArea"] textarea {
      font-size: 1.05rem !important;
      line-height: 1.35 !important;
    }
    label, .stCaption, [data-testid="stCaptionContainer"] {
      color: var(--macro-muted) !important;
    }
    .stButton > button,
    [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-primary"] {
      background: #2c2e2a !important;
      color: var(--macro-text) !important;
      border: 1px solid var(--macro-border-strong) !important;
      border-radius: 12px !important;
      min-height: 2.9rem;
      font-weight: 600;
    }
    .stButton > button:hover {
      border-color: var(--macro-green) !important;
      color: #dff8ee !important;
    }
    div[role="radiogroup"] {
      display: flex;
      gap: .65rem;
      flex-wrap: wrap;
    }
    div[role="radiogroup"] label {
      background: #2c2e2a;
      border: 1px solid var(--macro-border-strong);
      border-radius: 12px;
      padding: .68rem 1rem;
      margin: 0 !important;
      min-width: 6rem;
      justify-content: center;
    }
    div[role="radiogroup"] label:has(input:checked) {
      border-color: var(--macro-green);
      background: #213d34;
    }
    .app-header {
      display: flex;
      align-items: center;
      gap: 1rem;
      border-bottom: 1px solid var(--macro-border);
      padding: 1.2rem 1.5rem;
      margin: 0 -2.4rem 1.4rem;
      position: relative;
      z-index: 2;
    }
    .logo {
      width: 3rem;
      height: 3rem;
      border-radius: 14px;
      display: grid;
      place-items: center;
      background: var(--macro-green);
      color: white;
      font-weight: 800;
      letter-spacing: .02em;
    }
    .header-title {
      font-size: 1.9rem;
      line-height: 1.1;
      font-weight: 650;
    }
    .header-subtitle {
      color: var(--macro-muted);
      font-size: 1.05rem;
      margin-top: .35rem;
    }
    .results-title {
      color: var(--macro-text);
      font-size: 1.35rem;
      font-weight: 650;
      margin: 1.8rem 0 .8rem;
    }
    .recipe-card {
      border: 1px solid var(--macro-border);
      border-radius: 14px;
      padding: 1rem;
      margin: 1rem 0 .6rem;
      background: #252722;
    }
    .top-card { border-color: var(--macro-green); border-width: 2px; }
    .recipe-card-layout {
      display: grid;
      grid-template-columns: minmax(180px, 260px) 1fr;
      gap: 1rem;
      align-items: stretch;
    }
    .recipe-image {
      width: 100%;
      height: 100%;
      min-height: 210px;
      object-fit: cover;
      border-radius: 12px;
      border: 1px solid #3e403b;
      background: #1f211e;
    }
    .recipe-content {
      min-width: 0;
    }
    .recipe-card-header {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: flex-start;
      margin-bottom: .85rem;
    }
    .recipe-title { font-size: 1.12rem; font-weight: 650; color: var(--macro-text); }
    .recipe-meta { color: var(--macro-muted); font-size: .9rem; margin-top: .2rem; }
    .macro-badge {
      color: #bff4de;
      border: 1px solid #2f725b;
      background: var(--macro-green-soft);
      border-radius: 999px;
      padding: .25rem .7rem;
      white-space: nowrap;
      font-size: .82rem;
    }
    .score-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: .6rem;
      margin-bottom: .85rem;
    }
    .score-tile {
      text-align: center;
      background: #2c2e2a;
      border: 1px solid #3e403b;
      border-radius: 10px;
      padding: .55rem .25rem;
    }
    .score-value { color: #6de0b5; font-weight: 700; font-size: 1.1rem; }
    .score-label {
      color: var(--macro-dim);
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .05em;
    }
    .explanation { color: var(--macro-muted); line-height: 1.55; margin: .7rem 0; }
    .recipe-description {
      color: var(--macro-text);
      line-height: 1.5;
      margin: .25rem 0 .75rem;
    }
    .tag-label {
      color: var(--macro-dim);
      font-size: .78rem;
      text-transform: uppercase;
      letter-spacing: .06em;
      margin-top: .65rem;
    }
    [data-testid="stAlert"] {
      background: #332f23;
      color: var(--macro-text);
      border: 1px solid #74613b;
      border-radius: 12px;
    }
    @media (max-width: 900px) {
      [data-testid="stSidebar"] {
        min-width: auto;
        max-width: none;
      }
      .recipe-card-layout {
        grid-template-columns: 1fr;
      }
      .recipe-image {
        height: 220px;
      }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

profile_bundle = render_profile_sidebar()

st.markdown(
    """
    <div class="app-header">
      <div class="logo">MC</div>
      <div>
        <div class="header-title">MacroChef Agent</div>
        <div class="header-subtitle">
          Tell me what's in your fridge and I'll find recipes that fit your goals.
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info(
    "Building your personal recipe database? Open the Recipe Library Builder page "
    "from the sidebar, discover recipes, save them, then return here for recommendations."
)

planner_tab, trace_tab = st.tabs(["Meal planner", "System trace"])

with planner_tab:
    (
        input_type,
        typed_ingredients,
        confirmed_inventory,
        cuisine_preference,
        meal_type,
    ) = render_inventory_input(API_URL)

    if st.button("Find matching recipes", type="primary", width="stretch"):
        profile = profile_bundle["profile"]
        profile["preferred_cuisines"] = [] if cuisine_preference is None else [cuisine_preference]
        payload = {
            "user_id": "demo_user",
            "input_type": input_type,
            "typed_ingredients": typed_ingredients,
            "confirmed_inventory": confirmed_inventory or None,
            "user_profile": profile,
            "cuisine_preference": cuisine_preference,
            "meal_type": meal_type,
        }
        try:
            response = requests.post(f"{API_URL}/recipes/recommend", json=payload, timeout=90)
            response.raise_for_status()
            st.session_state["recommendation_response"] = response.json()
        except requests.RequestException as exc:
            st.error(f"Could not reach MacroChef API at {API_URL}: {exc}")

    response_json = st.session_state.get("recommendation_response")
    if response_json:
        errors = response_json.get("errors", [])
        if errors:
            st.warning(" ".join(errors))

        shopping = response_json.get("shopping_list", [])
        if shopping:
            st.markdown('<div class="results-title">Shopping list</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="tag-row">'
                + "".join(f'<span class="missing-tag">{item["name"]}</span>' for item in shopping)
                + "</div>",
                unsafe_allow_html=True,
            )

        render_recommendations(API_URL, response_json.get("recommendations", []))

with trace_tab:
    render_debug_panel(st.session_state.get("recommendation_response"))
