# Two-Minute Demo Script

1. Start the API with `uvicorn app.main:app --reload --port 8000`.
2. Start the UI with `streamlit run frontend/streamlit_app.py`.
3. In the sidebar, set `600` calories, `45g` protein, peanut allergy, Mediterranean cuisine, and `35` minutes.
4. Type `chicken breast, spinach, rice, bell pepper` and optionally upload a fridge or pantry photo.
5. Click `Extract Inventory`.
6. Click `Generate Meal Plan`.
7. Show the top three recipe cards, focusing on pantry match, macro fit, missing ingredients, and explanation.
8. Open the debug trace and point out graph steps and rejected recipes.
9. Change allergy to dairy and regenerate to show deterministic rejection of dairy-containing recipes.
10. Add an image alongside text to demonstrate multimodal extraction with confidence scores.

## 60-Second Recipe Library Builder Add-On

1. Open the Streamlit `Recipe Library Builder` page.
2. Select `Japanese` and `Indian`.
3. Ask for `10` high-protein dinners under `35` minutes.
4. Click `Discover recipes` and show the candidate cards.
5. Select three recipes and click `Save selected recipes`.
6. Return to the main MacroChef page.
7. Enter ingredients like `chicken breast, rice, spinach`.
8. Generate recommendations and point out that user-saved recipes can now appear beside base recipes.
