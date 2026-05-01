# MacroChef Agent

MacroChef Agent is a multimodal, constraint-aware meal planning system that turns a fridge photo or typed pantry list into safe, macro-aware recipe recommendations. It combines ChromaDB recipe RAG, a LangGraph workflow, deterministic allergy and nutrition logic, and a Streamlit product UI.

## Problem Statement
Generic recipe chatbots are weak at hard constraints. MacroChef treats meal planning as a structured decision workflow: extract inventory, retrieve feasible recipes, enforce allergies and dietary rules, score nutrition fit, rank meals, explain tradeoffs, and build a shopping list.

## Key Features

- Text inventory parsing, optional fuzzy ingredient normalization, and mock vision extraction that works without API keys
- ChromaDB RAG over a bundled 25-recipe JSONL corpus
- LangGraph nodes for intake, inventory confirmation, constraints, retrieval, safety filtering, scoring, ranking, explanation, procurement, and memory
- Separate Recipe Library Builder Agent for discovering, validating, saving, and indexing personal recipes
- Deterministic hard constraints for allergies, dislikes, diet type, and cook time
- Deterministic macro scoring from recipe metadata
- Structured Pydantic v2 API contracts
- SQLite user feedback memory
- Streamlit frontend with recipe cards, scores, shopping list, and debug trace
- Pytest coverage for parsing, constraints, scoring, retrieval, and graph flow

## Architecture

```text
Streamlit UI
   |
   v
FastAPI routes
   |
   v
LangGraph workflow
   |--> inventory parser / mock vision
   |--> inventory confirmation
   |--> constraint builder
   |--> ChromaDB recipe retriever + keyword fallback
   |--> deterministic safety filter
   |--> nutrition and pantry scoring
   |--> ranking and explanation
   |--> shopping list generation
   |--> SQLite memory
```

## Agent Workflow

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

Conditional handling:

- Empty inventory returns a friendly error.
- No valid recipes after filtering triggers fallback retrieval over all sample recipes.
- Low-confidence vision items are marked for confirmation.
- Chroma failures fall back to keyword search.

## RAG Design

`scripts/ingest_recipes.py` loads `data/processed/sample_recipes.jsonl`, creates a rich recipe document, stores recipe metadata, and persists the Chroma collection in `data/chroma`. Local sentence-transformers embeddings are attempted first; a deterministic hashing embedding fallback keeps offline demos runnable.

## Recipe Library Builder Agent

The Recipe Library Builder is a separate acquisition workflow. The meal planner answers, "Given my pantry and constraints, what should I cook?" The library builder answers, "Help me build a personalized recipe database."

```text
Streamlit Library Page
  -> POST /library/discover
  -> discovery_node
  -> normalization_node
  -> recipe_validation_node
  -> deduplication_node
  -> candidate_presentation_node
  -> POST /library/save
  -> SQLite structured recipe store
  -> ChromaDB recipe index
```

Users choose cuisines, meal type, diet type, cook time, difficulty, allergy exclusions, and preferences such as "minimal equipment" or "no deep frying." Candidate recipes are validated and deduplicated before they can be saved. Saved recipes are stored with `owner_user_id`, `is_user_saved`, source metadata, placeholder image URLs, estimated macros, and allergen tags.

The original recommendation workflow now retrieves from both the base recipe corpus and the current user's saved recipe library. Private recipes are filtered by `user_id`, so one user's saved recipes are not returned for another user.

Recipe Library API endpoints:

- `POST /library/discover`: generate or retrieve candidate recipes
- `POST /library/save`: save selected validated candidates
- `GET /library/{user_id}`: list saved recipes
- `DELETE /library/{user_id}/{recipe_id}`: deactivate a saved recipe
- `POST /library/reindex`: rebuild Chroma from base and user recipes

Example discovery request:

```json
{
  "user_id": "demo_user",
  "cuisines": ["Japanese", "Indian"],
  "meal_type": "dinner",
  "diet_type": "high-protein",
  "max_cook_time_min": 35,
  "difficulty": "easy",
  "count": 10,
  "home_cookable": true,
  "excluded_ingredients": [],
  "allergies": ["peanut"],
  "extra_preferences": "minimal equipment, no deep frying",
  "source_mode": "mock"
}
```

Example save request:

```json
{
  "user_id": "demo_user",
  "selected_candidates": [
    {
      "candidate_id": "mock_example",
      "title": "Teriyaki Chicken Rice Bowl",
      "cuisine": "Japanese",
      "meal_type": "dinner",
      "description": "A simple teriyaki-style chicken bowl.",
      "ingredients": ["150 g chicken breast", "150 g cooked rice", "90 g broccoli"],
      "instructions": ["Cook rice.", "Sear chicken.", "Serve with vegetables."],
      "cook_time_min": 25,
      "difficulty": "easy",
      "servings": 1,
      "calories": 590,
      "protein_g": 48,
      "carbs_g": 70,
      "fat_g": 12,
      "fiber_g": 6,
      "allergens": ["soy"],
      "diet_tags": ["high-protein", "dairy-free"],
      "equipment": ["skillet"],
      "source_type": "mock"
    }
  ]
}
```

## Constraint Engine

Allergies, disliked ingredients, diet type, and maximum cook time are hard constraints in `app/services/constraint_engine.py`. LLMs never enforce allergies and never calculate nutrition. Macro targets are soft constraints used only by the scorer.

## Multimodal Inventory Extraction

Typed inventory is parsed by comma, newline, or semicolon. The frontend also accepts an optional fridge or pantry image at the same time, then merges text and vision observations into one editable inventory table. Detected ingredients can be included or excluded with checkboxes, and missed items can be added manually before recommendation. If `rapidfuzz` is installed, common typos like `chikcen brest` can be normalized to known pantry names. Image extraction uses deterministic mock output by default:

- chicken breast
- spinach
- eggs
- bell pepper
- Greek yogurt
- rice

Each vision observation includes a confidence score and `needs_confirmation` if confidence is below `0.75`.

## Evaluation Metrics

- Allergy violation rate
- Pantry utilization rate
- Macro deviation
- Missing ingredient count
- Recommendation validity rate

Run:

```bash
python scripts/evaluate_demo_set.py
```

## Tech Stack

- Backend: FastAPI, Pydantic v2, Uvicorn, SQLAlchemy, SQLite
- Frontend: Streamlit, Requests, Pandas
- Agent: LangGraph
- RAG: ChromaDB, sentence-transformers, deterministic embedding fallback
- Optional AI providers: Gemini, OpenAI, Claude, and local Ollama
- Testing: Pytest
- Packaging: Docker, docker-compose

## Setup

Using `venv`:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Using Conda:

```bash
conda create -n macrochef-agent python=3.11 -y
conda activate macrochef-agent
pip install -r requirements.txt
cp .env.example .env
```

The default `.env.example` uses mock/local mode and requires no external API keys.

## Optional Model Provider Setup

Mock mode remains the default. If you provide API keys or run Ollama locally, MacroChef can use hosted or local models for image inventory extraction and recommendation explanations.

Install or update dependencies:

```bash
pip install -r requirements.txt
```

If you already installed the project before provider support was added, this smaller install is enough for Gemini:

Create `.env` if you have not already:

```bash
cp .env.example .env
```

Supported provider names:

- `mock`: deterministic demo mode, no API key
- `gemini` or `google`: Gemini API via `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- `openai`: OpenAI API via `OPENAI_API_KEY`
- `anthropic` or `claude`: Claude API via `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`
- `ollama` or `local`: local Ollama server via `OLLAMA_BASE_URL`

`MODEL_PROVIDER` is the primary provider. `MODEL_PROVIDER_FALLBACKS` is an ordered comma-separated list. If the primary provider is missing credentials, unavailable, or returns invalid output, MacroChef tries each fallback and finally uses `mock` so the app remains runnable.


## Ingest Recipes

```bash
python scripts/ingest_recipes.py
```

## Run API

```bash
uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Run Frontend

```bash
streamlit run frontend/streamlit_app.py
```

Open `http://localhost:8501`.

## Run Tests

```bash
pytest
```

## Example Request

Bash or macOS/Linux shell:

```bash
curl -X POST http://localhost:8000/recipes/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "input_type": "text",
    "typed_ingredients": "chicken breast, spinach, rice",
    "user_profile": {
      "user_id": "demo_user",
      "allergies": ["peanut"],
      "disliked_ingredients": [],
      "diet_type": null,
      "preferred_cuisines": ["Mediterranean"],
      "macro_targets": {
        "calories": 600,
        "protein_g": 45,
        "carbs_g": 60,
        "fat_g": 20,
        "fiber_g": 8
      },
      "max_cook_time_min": 35
    },
    "cuisine_preference": "Mediterranean",
    "meal_type": "dinner"
  }'
```

Windows PowerShell:

```powershell
$body = @'
{
  "user_id": "demo_user",
  "input_type": "text",
  "typed_ingredients": "chicken breast, spinach, rice",
  "user_profile": {
    "user_id": "demo_user",
    "allergies": ["peanut"],
    "disliked_ingredients": [],
    "diet_type": null,
    "preferred_cuisines": ["Mediterranean"],
    "macro_targets": {
      "calories": 600,
      "protein_g": 45,
      "carbs_g": 60,
      "fat_g": 20,
      "fiber_g": 8
    },
    "max_cook_time_min": 35
  },
  "cuisine_preference": "Mediterranean",
  "meal_type": "dinner"
}
'@

Invoke-RestMethod `
  -Uri "http://localhost:8000/recipes/recommend" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

## Example Response Shape

```json
{
  "recommendations": [
    {
      "recipe": {"recipe_id": "r_001", "title": "Mediterranean Chicken Rice Bowl"},
      "score": {
        "pantry_match_score": 0.5,
        "macro_fit_score": 0.91,
        "final_score": 0.72,
        "missing_ingredients": ["bell pepper", "Greek yogurt", "lemon"]
      },
      "explanation": "This recipe fits because...",
      "shopping_list": ["bell pepper", "Greek yogurt", "lemon"]
    }
  ],
  "shopping_list": [{"name": "bell pepper", "reason": "Needed for ..."}],
  "rejected_recipes": [],
  "debug_trace": [
    "intake_node: extracted 3 ingredients.",
    "inventory_confirmation_node: auto-confirmed 3 ingredients."
  ]
}
```

## Screenshots

## Limitations

- Not medical advice.
- Nutrition estimates depend on recipe metadata.
- Mock vision is deterministic and not a real image recognizer.
- Allergy safety depends on accurate recipe metadata and user input.
- Optional Gemini/OpenAI/Claude/Ollama integrations are isolated and disabled by default.

## Future Improvements

- Real provider-specific vision extraction with structured output validation
- Per-serving scaling and household preference profiles
- More granular ingredient quantities and unit conversion
- Recipe import pipeline from licensed public datasets
- Offline packaged embedding model for fully local semantic retrieval
- Human-in-the-loop confirmation before any high-risk allergy recommendation

## TL;DR

"MacroChef Agent is a multimodal, constraint-aware meal planning system that turns 
fridge photos or typed pantry lists into safe, macro-aware recipe recommendations. 
It uses a vision model to extract available ingredients, ChromaDB-based RAG to retrieve 
relevant recipes, deterministic validation to enforce allergies and dietary rules, and 
a LangGraph workflow to orchestrate inventory extraction, recipe retrieval, nutrition 
scoring, shopping-list generation, and user preference memory. Unlike a generic recipe 
chatbot, MacroChef Agent explains why each meal is feasible, safe, and aligned with 
the user's goals."
