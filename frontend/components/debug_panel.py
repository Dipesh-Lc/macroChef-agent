import streamlit as st


def render_debug_panel(response_json: dict | None) -> None:
    if not response_json:
        st.info("Run the meal planner to see graph steps, rejected recipes, and raw output.")
        return

    st.markdown("#### Rejected recipes")
    rejected = response_json.get("rejected_recipes", [])
    if rejected:
        for item in rejected:
            st.write(f"- {item['title']}: {item['reason']}")
    else:
        st.write("No hard-constraint rejections.")

    st.markdown("#### Graph trace")
    for step in response_json.get("debug_trace", []):
        st.write(f"- {step}")

    st.markdown("#### Raw JSON")
    st.json(response_json)
