import streamlit as st


def _add_tag(input_key: str, list_key: str) -> None:
    value = st.session_state.get(input_key, "").strip()
    if not value:
        return
    items = st.session_state.setdefault(list_key, [])
    if value.lower() not in {item.lower() for item in items}:
        items.append(value)
    st.session_state[input_key] = ""


def _render_tags(list_key: str) -> list[str]:
    items = st.session_state.setdefault(list_key, [])
    if items:
        st.markdown(
            '<div class="tag-row">'
            + "".join(f'<span class="profile-tag">{item}</span>' for item in items)
            + "</div>",
            unsafe_allow_html=True,
        )
    return items


def render_profile_sidebar() -> dict:
    with st.sidebar:
        st.markdown('<div class="sidebar-title">Profile</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Macro targets</div>', unsafe_allow_html=True)

        left, right = st.columns(2)
        with left:
            calories = st.number_input("Calories", min_value=0, value=2000, step=25)
            carbs = st.number_input("Carbs (g)", min_value=0.0, value=200.0, step=5.0)
        with right:
            protein = st.number_input("Protein (g)", min_value=0.0, value=150.0, step=5.0)
            fat = st.number_input("Fat (g)", min_value=0.0, value=65.0, step=2.0)

        st.markdown('<div class="section-label spaced">Allergies</div>', unsafe_allow_html=True)
        allergies = _render_tags("allergy_items")
        allergy_col, allergy_button_col = st.columns([0.72, 0.28])
        allergy_col.text_input(
            "Allergy",
            key="allergy_input",
            placeholder="e.g. peanuts",
            label_visibility="collapsed",
        )
        allergy_button_col.button(
            "Add",
            key="add_allergy",
            width="stretch",
            on_click=_add_tag,
            args=("allergy_input", "allergy_items"),
        )

        st.markdown('<div class="section-label spaced">Diet type</div>', unsafe_allow_html=True)
        diet_type = st.selectbox(
            "Diet type",
            ["Any", "vegetarian", "vegan", "gluten-free", "dairy-free"],
            index=0,
            label_visibility="collapsed",
        )

        st.markdown('<div class="section-label spaced">Max cook time</div>', unsafe_allow_html=True)
        max_time_label = st.selectbox(
            "Max cook time",
            ["No limit", "15 min", "30 min", "45 min", "60 min"],
            index=0,
            label_visibility="collapsed",
        )

        st.markdown('<div class="section-label spaced">Disliked ingredients</div>', unsafe_allow_html=True)
        disliked = _render_tags("dislike_items")
        dislike_col, dislike_button_col = st.columns([0.72, 0.28])
        dislike_col.text_input(
            "Disliked ingredient",
            key="dislike_input",
            placeholder="e.g. cilantro",
            label_visibility="collapsed",
        )
        dislike_button_col.button(
            "Add",
            key="add_dislike",
            width="stretch",
            on_click=_add_tag,
            args=("dislike_input", "dislike_items"),
        )

        st.markdown('<div class="section-label spaced">Fiber target</div>', unsafe_allow_html=True)
        fiber = st.number_input(
            "Fiber (g)",
            min_value=0.0,
            value=25.0,
            step=1.0,
            label_visibility="collapsed",
        )

        st.markdown('<div class="section-label spaced">Servings</div>', unsafe_allow_html=True)
        st.selectbox("Servings", ["1 person", "2 people", "4 people"], index=1, label_visibility="collapsed")

    max_time = None if max_time_label == "No limit" else int(max_time_label.split()[0])
    return {
        "profile": {
            "user_id": "demo_user",
            "allergies": allergies,
            "disliked_ingredients": disliked,
            "diet_type": None if diet_type == "Any" else diet_type,
            "preferred_cuisines": [],
            "macro_targets": {
                "calories": calories or None,
                "protein_g": protein or None,
                "carbs_g": carbs or None,
                "fat_g": fat or None,
                "fiber_g": fiber or None,
            },
            "max_cook_time_min": max_time,
        }
    }
