import requests
import streamlit as st


def render_saved_recipe_library(api_url: str, user_id: str) -> None:
    st.markdown('<div class="results-title">My recipe library</div>', unsafe_allow_html=True)
    if st.button("Refresh saved recipes", width="stretch"):
        st.session_state.pop("saved_library_response", None)

    if "saved_library_response" not in st.session_state:
        try:
            response = requests.get(f"{api_url}/library/{user_id}", timeout=30)
            response.raise_for_status()
            st.session_state["saved_library_response"] = response.json()
        except requests.RequestException as exc:
            st.error(f"Could not load recipe library: {exc}")
            return

    recipes = st.session_state.get("saved_library_response", {}).get("recipes", [])
    if not recipes:
        st.caption("No saved recipes yet.")
        return

    for recipe in recipes:
        with st.container(border=True):
            cols = st.columns([0.78, 0.22])
            with cols[0]:
                st.markdown(f"**{recipe['title']}**")
                st.caption(
                    f"{recipe.get('cuisine') or 'Any cuisine'} | "
                    f"{recipe.get('meal_type') or 'meal'} | "
                    f"{recipe.get('cook_time_min') or '?'} min"
                )
                st.write(recipe.get("description") or "")
            if cols[1].button("Delete", key=f"delete_{recipe['recipe_id']}", width="stretch"):
                try:
                    response = requests.delete(
                        f"{api_url}/library/{user_id}/{recipe['recipe_id']}",
                        timeout=30,
                    )
                    response.raise_for_status()
                    st.session_state.pop("saved_library_response", None)
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Could not delete recipe: {exc}")
