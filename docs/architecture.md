# Architecture

## System Architecture

```text
User
  |
  v
Streamlit frontend
  |
  v
FastAPI backend
  |
  +--> Inventory extraction service
  +--> Model provider router (mock, Gemini, OpenAI, Claude, Ollama)
  +--> LangGraph workflow
  +--> ChromaDB recipe retrieval
  +--> Deterministic constraint engine
  +--> Nutrition scorer
  +--> SQLite feedback memory
```

## Graph Workflow

```text
START
  -> intake_node
  -> inventory_confirmation_node
  -> constraint_builder_node
  -> recipe_retriever_node
  -> safety_filter_node
  -> nutrition_scoring_node
  -> meal_ranking_node
  -> chef_explanation_node
  -> procurement_node
  -> memory_update_node
  -> END
```

The graph has explicit conditional paths for empty inventory, inventory confirmation, retrieval fallback, and no valid recipes after filtering.

## Recipe Library Builder Flow

```text
Streamlit Library Page
  -> POST /library/discover
  -> Recipe Library Builder Graph
  -> Discovery / Generation
  -> Normalization
  -> Validation
  -> Deduplication
  -> Candidate Review
  -> POST /library/save
  -> Structured Recipe Store
  -> ChromaDB Index
```

The library builder is intentionally independent from the recommendation graph. It runs only when the user wants to acquire or generate recipes for their personal library.

## Data Flow

1. Inventory arrives as typed text, manual confirmed items, image upload, or combined text plus image input.
2. Ingredients are normalized and represented as `InventoryObservation`.
3. The confirmation node turns checked or trusted observations into `ConfirmedIngredient`.
4. User constraints are built from `UserProfile`.
5. RAG retrieves candidate recipes from base recipes and the current user's saved recipes.
6. Hard constraints reject unsafe recipes before scoring or explanation.
7. Scores combine pantry match, macro fit, time fit, and preference fit.
8. Top recipes produce explanations through the configured provider chain.
9. Feedback and session summary are written to SQLite.

## Model Provider Routing

`MODEL_PROVIDER` selects the primary provider. `MODEL_PROVIDER_FALLBACKS` is an ordered comma-separated list of backups. Supported values are `mock`, `gemini`, `openai`, `anthropic`/`claude`, and `ollama`/`local`.

Providers are only used for two non-authoritative tasks:

- image inventory extraction with confidence scores
- friendly recipe explanations

Allergy filtering, diet validation, cook-time checks, recipe macros, and macro scoring remain deterministic Python logic.

## RAG Indexing

`app/rag/preprocess.py` turns each recipe into a document containing title, cuisine, meal type, ingredients, diet tags, and description. Metadata stores recipe id, cuisine, meal type, cook time, macros, and allergen flags. `app/rag/build_index.py` writes these into ChromaDB.

User-saved recipes are stored in SQLite and indexed with metadata fields such as `owner_user_id`, `is_user_saved`, `source_type`, and allergen flags. Recommendation retrieval loads base recipes plus recipes where `owner_user_id` matches the request user.

## Memory Design

SQLite stores:

- user id
- recipe id
- feedback type
- timestamp
- notes

Liked or cooked recipes slightly increase preference score. Disliked or skipped recipes reduce it.
