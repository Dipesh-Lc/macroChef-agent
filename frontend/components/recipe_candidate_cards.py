import streamlit as st


def _macro_line(candidate: dict) -> str:
    return (
        f"{candidate.get('calories') or 0:.0f} calories | "
        f"{candidate.get('protein_g') or 0:.0f}g protein | "
        f"{candidate.get('carbs_g') or 0:.0f}g carbs | "
        f"{candidate.get('fat_g') or 0:.0f}g fat"
    )


def render_recipe_candidate_cards(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    st.markdown('<div class="results-title">Candidate recipes</div>', unsafe_allow_html=True)
    selected: list[dict] = []
    for index, candidate in enumerate(candidates, start=1):
        with st.container(border=True):
            top_cols = st.columns([0.08, 0.22, 0.7])
            should_save = top_cols[0].checkbox(
                "Save",
                value=index <= 3,
                key=f"save_candidate_{candidate['candidate_id']}",
                label_visibility="collapsed",
            )
            image = candidate.get("image_url") or candidate.get("image_path")
            if image:
                top_cols[1].image(image, width="stretch")
            with top_cols[2]:
                st.subheader(candidate["title"])
                st.caption(
                    " | ".join(
                        [
                            str(candidate.get("cuisine") or "Any cuisine"),
                            str(candidate.get("meal_type") or "meal"),
                            f"{candidate.get('cook_time_min') or '?'} min",
                            str(candidate.get("difficulty") or "difficulty n/a"),
                            str(candidate.get("source_type") or "source n/a"),
                        ]
                    )
                )
                st.write(candidate.get("description") or "No description provided.")
                st.write(_macro_line(candidate))

            st.markdown("**Ingredients**")
            st.write(", ".join(candidate.get("ingredients") or []))
            if candidate.get("diet_tags"):
                st.markdown("**Diet tags:** " + ", ".join(candidate["diet_tags"]))
            if candidate.get("allergens"):
                st.markdown("**Allergens:** " + ", ".join(candidate["allergens"]))
            if candidate.get("validation_warnings"):
                st.warning(" | ".join(candidate["validation_warnings"]))

            with st.expander("Instructions"):
                for step_index, step in enumerate(candidate.get("instructions") or [], start=1):
                    st.write(f"{step_index}. {step}")

        if should_save:
            selected.append(candidate)

    return selected
