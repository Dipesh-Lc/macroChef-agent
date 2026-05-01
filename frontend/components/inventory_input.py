from __future__ import annotations

import pandas as pd
import requests
import streamlit as st


def _option_radio(label: str, options: list[str], index: int = 0, key: str | None = None) -> str:
    st.markdown(f'<div class="step-label">{label}</div>', unsafe_allow_html=True)
    return st.radio(
        label,
        options,
        index=index,
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )


def _manual_inventory_row(name: str, quantity: str | None = None) -> dict:
    return {
        "raw_name": name,
        "normalized_name": name.strip(),
        "quantity": quantity.strip() if quantity and quantity.strip() else None,
        "confidence": 1.0,
        "source": "manual",
        "needs_confirmation": False,
        "include": True,
    }


def render_inventory_input(
    api_url: str,
) -> tuple[str, str | None, list[dict], str | None, str | None]:
    cuisine = _option_radio(
        "Your cuisine preference",
        ["Any", "Mediterranean", "Mexican", "Italian", "Indian", "Japanese", "American", "Thai"],
        key="cuisine_choice",
    )

    st.markdown(
        '<div class="step-label spaced">Fridge & pantry inventory</div>',
        unsafe_allow_html=True,
    )

    typed_ingredients = st.text_area(
        "Typed ingredients",
        value=st.session_state.get(
            "typed_ingredients",
            (
                "chicken breast, spinach, eggs, garlic, olive oil, rice, lemon, "
                "Greek yogurt, bell peppers, onions"
            ),
        ),
        height=140,
        label_visibility="collapsed",
        placeholder=(
            "List everything you have, e.g. chicken breast, spinach, eggs, "
            "garlic, olive oil, rice"
        ),
    )
    st.session_state["typed_ingredients"] = typed_ingredients
    st.caption("Separate ingredients with commas. You can also add a fridge or pantry photo.")

    upload = st.file_uploader(
        "Optional fridge or pantry photo",
        type=["jpg", "jpeg", "png", "webp"],
        key="inventory_photo",
    )

    detected = st.session_state.get("detected_inventory", [])
    if st.button("Extract inventory", width="stretch"):
        if not typed_ingredients.strip() and upload is None:
            st.warning("Add typed ingredients, upload an image, or use both.")
        else:
            data = {"typed_ingredients": typed_ingredients}
            files = None
            timeout = 30
            if upload is not None:
                files = {"image": (upload.name, upload.getvalue(), upload.type)}
                timeout = 60
            response = requests.post(
                f"{api_url}/inventory/extract",
                data=data,
                files=files,
                timeout=timeout,
            )
            response.raise_for_status()
            detected = response.json()
            st.session_state["detected_inventory"] = detected

    if detected:
        table = pd.DataFrame(detected)
        if "include" not in table.columns:
            table.insert(0, "include", True)
        for column, default in {
            "quantity": "",
            "confidence": 1.0,
            "needs_confirmation": False,
        }.items():
            if column not in table.columns:
                table[column] = default

        edited = st.data_editor(
            table[
                [
                    "include",
                    "normalized_name",
                    "quantity",
                    "confidence",
                    "needs_confirmation",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "include": st.column_config.CheckboxColumn("Use", default=True),
                "normalized_name": st.column_config.TextColumn("Ingredient", required=True),
                "quantity": "Quantity",
                "confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0,
                    max_value=1,
                ),
                "needs_confirmation": st.column_config.CheckboxColumn("Review"),
            },
            disabled=["confidence"],
            key="detected_inventory_editor",
        )

        add_name_col, add_qty_col, add_btn_col = st.columns([0.5, 0.32, 0.18])
        manual_name = add_name_col.text_input(
            "Add ingredient",
            placeholder="Add missed ingredient",
            key="manual_inventory_name",
            label_visibility="collapsed",
        )
        manual_quantity = add_qty_col.text_input(
            "Quantity",
            placeholder="Quantity optional",
            key="manual_inventory_quantity",
            label_visibility="collapsed",
        )
        if add_btn_col.button("Add", width="stretch", key="manual_inventory_add"):
            if manual_name.strip():
                st.session_state["detected_inventory"] = [
                    *edited.to_dict("records"),
                    _manual_inventory_row(manual_name, manual_quantity),
                ]
                st.rerun()
            st.warning("Enter an ingredient name before adding it.")

        edited_records = edited.to_dict("records")
        st.session_state["detected_inventory"] = edited_records
        confirmed = [
            {
                "name": row["normalized_name"],
                "quantity": row.get("quantity") or None,
                "expires_soon": False,
            }
            for row in edited_records
            if row.get("include", True) and row.get("normalized_name")
        ]
        st.session_state["confirmed_inventory"] = confirmed
    else:
        confirmed = st.session_state.get("confirmed_inventory", [])

    meal_type = _option_radio(
        "Meal type",
        ["breakfast", "lunch", "dinner"],
        index=2,
        key="meal_choice",
    )

    has_text = bool(typed_ingredients.strip())
    has_image = upload is not None
    if has_text and has_image:
        input_type = "mixed"
    elif has_image:
        input_type = "image"
    elif has_text:
        input_type = "text"
    else:
        input_type = "manual"

    return (
        input_type,
        typed_ingredients,
        confirmed,
        None if cuisine == "Any" else cuisine,
        meal_type,
    )
