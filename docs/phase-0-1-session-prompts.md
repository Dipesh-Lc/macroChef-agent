# Claude Code Session Prompts — Phase 0 & Phase 1

How to use this file:
- Run **one session per item, in order**. Each session = one branch = one PR you review and merge.
- For every item: press **Shift+Tab to enter plan mode first**, paste the prompt, review the plan, approve, let it implement, then review the diff and merge.
- Default model: `/model opusplan`. Where an item benefits from heavier reasoning, a note says so.
- Every prompt already tells the agent to run tests and show results — hold it to that before merging.

Recommended execution order (dependencies in parentheses):
0.1 → 0.2 → 1.1 (USDA client) → 1.2 (quantities, blocking) → 1.3 (corpus import) → 1.4 (macro re-derivation, needs 1.1 + 1.2 + 1.3)

---

## Phase 0 — Credibility Baseline

### 0.1 — Honest README + repo hygiene
Model: opusplan (Sonnet is plenty for execution)

> Read docs/ROADMAP.md and the whole repo. We're doing Phase 0. Rewrite the README so the headline is the real differentiator — "the LLM never enforces allergies or computes nutrition; deterministic code does" — and reframe the fridge-photo/vision feature honestly as optional/experimental rather than a headline, since it's currently mock. Also add a clear quickstart, a complete `.env.example` with every key the app reads (placeholders only), and a one-command local-run instruction. Leave visible TODO markers where a screenshot or demo GIF needs to be dropped in later (I'll add those myself). Show me the proposed README before writing files. Don't touch application logic in this PR.

### 0.2 — Vision: make it real or cleanly demote it
Model: opusplan

> Phase 0. Audit how the vision / fridge-photo path currently works and confirm it's mock by default. Give me two concrete options with effort estimates: (a) wire one real vision provider behind the existing interface with validated structured output and a fallback to mock, or (b) cleanly demote vision to an optional experimental module so it's no longer implied to be core. List the files each option touches. Recommend one. Don't implement until I choose.

---

## Phase 1 — Trust & Data Grounding

### 1.1 — Ground nutrition in USDA FoodData Central
Model: opusplan

> Phase 1, item 1. Add a nutrition-grounding module that computes macros from a real database instead of recipe-tag metadata. Plan a client for USDA FoodData Central (free API key, read from .env — add a placeholder to .env.example and tell me to fill it in). Requirements: ingredient-name → food match with a caching layer so we don't refetch, per-100g macro retrieval, a function that computes a recipe's macros from its quantity-aware ingredient list (note: this depends on item 1.2, so design the interface to accept `{name, amount, unit}` even though the quantity model lands next), graceful degradation if the API is unavailable, and Pydantic types for all responses. Add unit tests that check computed macros against a few known USDA reference values. List every file you'll touch and the tests you'll add before writing code.

### 1.2 — Quantity- and unit-aware inventory (BLOCKING PREREQUISITE)
Model: **Opus** (`/model opus` for planning — this is the schema everything else depends on)

> Phase 1, item 2 — the blocking prerequisite for the rest of the roadmap. Make ingredients quantity- and unit-aware everywhere. Plan: (1) a Pydantic ingredient model `{name, amount, unit}`; (2) a unit-conversion layer covering g/kg/oz/lb/ml/l/tsp/tbsp/cup/piece with sensible density handling where volume↔weight is needed, and clear behavior when conversion is impossible; (3) a migration path for the existing 25 recipes and any stored pantry/inventory data — decide and propose whether legacy name-only ingredients become optional-quantity or must be backfilled, and flag this as a decision for me; (4) update `pantry_match_score` and the shopping-list logic to be amount-aware (e.g. "have 200g chicken, need 500g" → short by 300g). Enumerate every file touched, the migration approach, and the full test list. This is safety-adjacent for portion-based macros, so be thorough. Do NOT write code until I approve the plan and the migration decision.

### 1.3 — Scale the recipe corpus
Model: opusplan (Haiku fine for any bulk reformatting sub-steps)

> Phase 1, item 3. We need to grow the corpus from 25 recipes to thousands so the RAG architecture is actually justified. First: research candidate open datasets (e.g. RecipeNLG, Recipe1M+, Open Food Facts recipes), and for each show me its license and whether our use is permitted — do not import anything until I confirm a license. Then plan an import pipeline that maps external records into our schema, including the quantity-aware ingredient model from item 1.2, deduplicates, validates with our Pydantic contracts, drops malformed records, and rebuilds the vector store. Make it idempotent and re-runnable. Report how many recipes survive validation. Show me the dataset options and the pipeline plan before importing.

### 1.4 — Re-derive macros for the whole corpus
Model: opusplan

> Phase 1, item 4 (depends on 1.1, 1.2, 1.3). Now that recipes have quantity-aware ingredients and we have the USDA nutrition module, plan a batch job that recomputes macros for every recipe in the corpus from real ingredient data, replacing self-reported tag values. Requirements: run it as a re-runnable script (default it to Sonnet-level work if headless), cache USDA lookups aggressively to control cost, produce a report of recipes where computation failed or looked implausible (e.g. per-serving kcal outside a sane range) for my review rather than silently writing bad data, and keep the old values recoverable in case we need to compare. After the run, update any code paths that still read tag-based macros to use computed macros. Show me the plan and the implausibility thresholds before running.

---

## Phase 1 exit checklist (verify before moving to Phase 2)

Run these yourself; don't take the agent's word:
- [ ] `pytest` green, including new unit-conversion and macro-computation tests
- [ ] Any recipe's macros are computed from USDA data, not tags
- [ ] Pantry matching accounts for amounts, not just presence
- [ ] Corpus is at target scale with a documented, permitted dataset license
- [ ] Retrieval eval shows semantic RAG beating a keyword baseline on a ~50-query set
- [ ] Existing allergy/constraint tests still pass at the new corpus scale (violation rate still 0)

When all six are checked, start Phase 2 with the benchmark work.
