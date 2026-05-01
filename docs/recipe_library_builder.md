# Recipe Library Builder Agent

The Recipe Library Builder Agent is a separate workflow from the MacroChef meal recommendation agent.

The meal planner answers: "Given my current pantry and constraints, what should I cook?"

The library builder answers: "Help me build a personal recipe database by cuisine, meal type, diet, cook time, and home-cooking preferences."

## User Flow

1. Open the Streamlit `Recipe Library Builder` page.
2. Choose cuisines, meal type, diet type, max cook time, difficulty, count, allergies, excluded ingredients, and extra preferences.
3. Click `Discover recipes`.
4. Review structured candidate cards.
5. Select recipes to save.
6. Save selected recipes into the personal recipe library.
7. Return to the meal planner; saved recipes can now be retrieved alongside base recipes.

## Backend Flow

```text
POST /library/discover
  -> Recipe Library Builder Graph
  -> discovery_node
  -> normalization_node
  -> recipe_validation_node
  -> deduplication_node
  -> candidate_presentation_node

POST /library/save
  -> selected_candidate_validation_node
  -> save_recipe_node
  -> index_recipe_node
```

## Validation

Candidates are validated with Pydantic and deterministic checks before they are shown or saved. The validation service rejects missing titles, too few ingredients, too few instructions, allergy conflicts, excluded ingredients, and cook-time violations. Missing macros, missing equipment, or generated nutrition estimates become warnings.

## Deduplication

The MVP deduplicates against current candidates, base recipes, and the user's saved recipes. It flags exact normalized title matches, near title matches, and high ingredient overlap within the same cuisine.

## Image Policy

The MVP uses deterministic placeholder image URLs by cuisine or meal type. It does not scrape or store copyrighted images.

## Retrieval Integration

Saved recipes are stored in SQLite and indexed into ChromaDB when available. If Chroma is unavailable, the existing keyword fallback still retrieves user recipes from the structured store. The recommendation flow only loads recipes saved by the active `user_id`, so one user's private recipe library is not retrieved for another user.

## Limitations

- Mock discovery is deterministic and intended for local demos.
- LLM generation is optional and still passes through validation.
- Nutrition is an estimate from candidate metadata, not a clinical nutrition calculation.
- Serving scaling and quantified shopping amounts are planned future improvements.
