import streamlit as st


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def render_library_builder_form() -> dict:
    st.markdown(
        '<div class="results-title">Discover recipes for your library</div>',
        unsafe_allow_html=True,
    )

    user_id = st.text_input("User ID", value=st.session_state.get("library_user_id", "demo_user"))
    st.session_state["library_user_id"] = user_id

    cuisines = st.multiselect(
        "Cuisines",
        ["Italian", "Indian", "Japanese", "Chinese", "Mexican", "Mediterranean", "American"],
        default=["Japanese", "Indian"],
    )
    col_a, col_b, col_c = st.columns(3)
    meal_type = col_a.selectbox("Meal type", ["Any", "breakfast", "lunch", "dinner"], index=3)
    diet_type = col_b.selectbox(
        "Diet type",
        ["Any", "high-protein", "vegetarian", "vegan", "dairy-free", "gluten-free"],
        index=1,
    )
    difficulty = col_c.selectbox("Difficulty", ["Any", "easy", "medium", "hard"], index=1)

    col_d, col_e = st.columns(2)
    max_cook_time = col_d.slider("Max cook time", min_value=10, max_value=90, value=35, step=5)
    count = col_e.select_slider("Recipes to discover", options=[5, 10, 15, 20], value=10)

    col_f, col_g = st.columns(2)
    allergies = _split_csv(col_f.text_input("Allergens to avoid", placeholder="peanut, shellfish"))
    excluded = _split_csv(
        col_g.text_input("Excluded ingredients", placeholder="cilantro, mushrooms")
    )

    extra_preferences = st.text_area(
        "Extra preferences",
        placeholder="home-cookable, no deep frying, minimal equipment",
        height=90,
    )
    source_mode = st.selectbox("Source mode", ["mock", "llm", "external", "hybrid"], index=0)
    home_cookable = st.checkbox("Prioritize home-cookable recipes", value=True)

    return {
        "user_id": user_id,
        "cuisines": cuisines,
        "meal_type": None if meal_type == "Any" else meal_type,
        "diet_type": None if diet_type == "Any" else diet_type,
        "max_cook_time_min": max_cook_time,
        "difficulty": None if difficulty == "Any" else difficulty,
        "count": count,
        "home_cookable": home_cookable,
        "excluded_ingredients": excluded,
        "allergies": allergies,
        "extra_preferences": extra_preferences or None,
        "source_mode": source_mode,
    }
