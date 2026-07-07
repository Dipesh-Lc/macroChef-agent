# MacroChef Agent — Consolidated Upgrade & Launch Roadmap

Merged plan from both reviews (Opus 4.8 + Fable 5). Organized so each phase has a clear goal, tasks, testing/evaluation gates, and an exit criterion. Sequenced so you deploy publicly at the end of Phase 2 — not at the very end — and iterate on real user signal.

**Product thesis (agreed by both models):** MacroChef is not "a recipe LLM." It is a *deterministic meal-planning and food-safety engine* that uses an LLM only for the fuzzy parts. Every phase below either proves that thesis, deepens it, or distributes it.

**Target audience (pick a niche, don't build for "everyone with a fridge"):** macro-trackers, lifters, meal-preppers, cut-phase dieters. The name macroChef already speaks to them.

---

## Phase 0 — Credibility Baseline (≈1 week)

**Goal:** Remove everything that makes a stranger distrust the repo in the first 60 seconds.

### Tasks
1. **Fix the vision story.** Either wire one real vision provider with validated structured output, or demote "fridge photo" from headline to "optional/experimental" and lead with the constraint-engine story instead. Do not headline a mock feature.
2. **Fill in README screenshots** (currently TODO) — 3 good screenshots + a 60–90 second demo GIF/clip.
3. **Rewrite the README pitch** around the real differentiator: "the LLM never enforces allergies or computes nutrition — deterministic code does."
4. **Repo hygiene:** clear quickstart, .env.example, one-command local run.

### Exit criterion
A stranger landing on the repo understands what's special within one minute and can run it locally in five.

---

## Phase 1 — Trust & Data Grounding (≈2–3 weeks)

**Goal:** Make the numbers real. This phase is the prerequisite for everything else.

### Tasks
1. **Ground nutrition in a real database.** Integrate USDA FoodData Central (free API) and/or Open Food Facts. Compute macros from actual ingredient data instead of trusting recipe-tag metadata. This kills the biggest credibility gap and lets you score *arbitrary* recipes.
2. **Quantity- and unit-aware inventory (blocking prerequisite).** Ingredients become `{name, amount, unit}` with a unit-conversion layer (g/oz/cups/pieces). Without this, pantry-match scores and shopping lists are structurally fake. Every later feature (planner, cost, waste, batch solver) depends on it.
   - **Follow-up (do after 2, before/with 4): author real quantities for the 25 seed recipes.** Item 2 makes the data model quantity-aware but leaves the seed corpus name-only (`amount: null`), so pantry-shortfall math and USDA grounding aren't yet exercised on the flagship recipes. Author real, researched quantities for all 25 seed recipes; prefer mass units the conversion layer can reconcile so the demo path shows true shortfalls and grounded macros.
3. **Scale the recipe corpus** from 25 to thousands via an open dataset (RecipeNLG, Recipe1M+, Open Food Facts — verify each license before shipping). This is what makes the RAG architecture actually justified.
   - **Requirement — surface dropped empty ingredients at import.** Item 2 drops empty/whitespace-name ingredients when a `Recipe` is assembled and logs each drop at `DEBUG` (correct for runtime, but invisible by default). The corpus-import pipeline must additionally tally these drops and emit an **aggregate count at `INFO` at the end of the import run** (e.g. "dropped N empty ingredients across M recipes"), so systematic empty-production in the source dataset is visible by default during import rather than only under `DEBUG`.
   - **First cut capped at ~5,000 (license: CC0 only — RecipeNLG/Recipe1M+ are non-commercial-only and were ruled out for the shipped corpus).** If that import passes validation/dedup/quality checks cleanly, schedule a follow-up "top-up" import toward thousands+ as a fast-follow item rather than importing the full source dataset in the first pass.
   - **Source: [irkaal/foodcom-recipes-and-reviews](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews) (CC0), imported via `scripts/import_corpus.py`.** Chosen for hobby/non-commercial use, where CC0 is low-risk even though the data is evidently scraped from the live Food.com site with CC0 self-applied by the Kaggle uploader (not granted by Food.com). **If this project moves toward commercial/public deployment, revisit the imported-recipe data source and licensing before scaling** — the separate `imported_recipes.jsonl` layout (seeds untouched in `sample_recipes.jsonl`, imports unioned in at index time) makes swapping or removing the corpus a cheap delete-and-reimport rather than a foundation rebuild.
4. **Re-derive macros for the imported corpus** using the new nutrition DB so all recipes have computed (not self-reported) nutrition.
   - **Follow-up (found during 1.4, not fixed):** `recipe_indexing_service.py` still embeds tag-based macros into the Chroma embedding text at corpus-build time. Re-point it to read computed-or-unknown via `nutrition_view`, same as the scorer/frontend/explanation paths — requires a full reindex, so scope it as its own change.
   - **Follow-up (found during 1.4, not fixed):** `RecipeRetriever._base_recipes` only ever loads the 25 seeds (`load_recipes()`), never the seed+imported union (`load_corpus()`). The 4,238 imported recipes are embedded in Chroma and searchable, but `retrieve()`'s `recipes_by_id` lookup filters their ids out since they're absent from `_base_recipes` — they never actually surface in a recommendation. Wire the retriever to the full corpus. **Relevant to this phase's own "RAG vs. keyword baseline" eval below** — that eval can't be measuring what it claims to while the imported corpus is invisible to retrieval.
   - **Closed for the 25 seeds, not generalized to the imported corpus (Step B closeout, item 1.4):** the grounding engine's matching mechanism (nutrient-number fallback, query-augmentation + relevance check, retry/cache reproducibility, two-tier generic-then-Branded fetch, `preparation`-gated raw/cooked/canned matching) is solid and reproducible (verified via repeated clean-cache runs with zero drift). But several residuals were found and individually investigated only for the 25 seeds, not the corpus at large — see `grounding_job.py`'s `_KNOWN_RESIDUALS` (rendered in every `grounding_report.md`) for the live, authoritative list:
     - **Undeclared-preparation same-food-wrong-state matches** (the general case): any ingredient without a declared `preparation` can land on a processed/wrong-state record purely by dataType-tier order (this is what chicken breast, ground turkey, corn, and tofu hit before being individually audited and fixed with `preparation="raw"` for the seeds). Unaudited for the imported corpus — likely affects some nonzero fraction of it.
     - **Sibling-food/synonym ambiguity**: FDC sometimes files a food's canonical record under a different head noun than its common name (zucchini → "Squash"; almonds → "Nuts"), which the relevance check's head-noun rule correctly refuses to bridge without a synonym table it doesn't have. No generalized fix exists yet.
     - **Branded same-name-different-value noise and 0-kcal data defects**: confirmed real (Branded "GREEK YOGURT" ranged 65-467 kcal/100g pre-fix; "CHILI POWDER"/"GINGER" report literal 0 kcal). The two-tier fetch mitigates this for ingredients with a real generic alternative, but doesn't eliminate it corpus-wide, and the 0-kcal defect class has no general detection yet (handled via an explicit, disclosed exclusion list for the two seeds that hit it).
   - **Follow-up (found during 1.4, not fixed):** the USDA grounding fixes landed in 1.4 (nutrient-number fallback, query-augmentation + relevance check, retry/cache reproducibility, `preparation`-gated raw/cooked/canned matching) only cover the 25 hand-authored seeds — either because a fix was applied directly to specific seed ingredients (carrot/seaweed → `preparation="raw"`, egg → renamed to "whole egg"), or because the underlying mechanism (query augmentation, relevance check) was only exercised against seed ingredient names. Two unresolved gaps generalize to the whole corpus and need a real design decision, not a per-ingredient patch:
     1. **Undeclared-preparation same-food-wrong-state matches.** Any ingredient without a declared `preparation` (i.e. everything except the 25 seeds' grain/legume/pasta occurrences) can still land on a processed/wrong-state USDA record purely by `_DATA_TYPE_PRIORITY` tie-order (e.g. zucchini → "Zucchini, pickled" instead of raw — confirmed still unresolved even with `preparation="raw"` declared, since FDC's canonical zucchini record is filed under "Squash," not "Zucchini," and the relevance check's head-noun rule correctly refuses to guess the two are the same food without a synonym table).
     2. **Branded-catalog same-name-different-value noise.** FDC's Branded dataset can return multiple products under an identical generic name with wildly different self-reported calories (confirmed live: "GREEK YOGURT" ranges 65-467 kcal/100g across 5 Branded entries; "BALSAMIC VINEGAR" ranges 67-300 kcal/100g) — `_best_match` has no defense against this beyond FDC's own arbitrary response order, so a "grounded" recipe can silently rest on the worst of several same-named candidates. This is a distinct root cause from the relevance/preparation work and needs its own fix (e.g. preferring a median/typical value among same-named duplicates, or additional dataType deprioritization for generic ingredient names).

### Testing / evaluation gates
- Unit tests for unit conversion and macro computation against known USDA reference values.
- Retrieval eval: semantic RAG vs. keyword baseline on ~50 queries; RAG must measurably win (otherwise the corpus/embedding setup needs work).
- Regression: existing allergy/constraint tests still pass at the new corpus scale.

### Exit criterion
Any recipe in the system has macros computed from real ingredient data, and pantry matching accounts for amounts.

---

## Phase 2 — Prove the Thesis Publicly: Safety Benchmark + First Deploy (≈2 weeks)

**Goal:** Produce the single most shareable artifact this project can generate, then go live.

### Tasks
1. **Build and publish a safety benchmark.**
   - Author 300–500 adversarial test cases: allergy stated then contradicted later in conversation, hidden allergens ("satay sauce" → peanut), diet-type traps (vegan → hidden gelatin/fish sauce), macro-limit traps.
   - Run raw GPT / Claude / Gemini prompting vs. MacroChef on the same cases.
   - Publish the violation-rate comparison table in the README + a short blog post. Target claim shape: "0 allergy violations across N adversarial cases vs X% for direct LLM prompting."
   - Make the harness reproducible (one script, pinned cases) so others can verify.
2. **First public deployment (minimum viable stack):**
   - Backend: Render / Railway / Fly.io.
   - DB: SQLite → managed Postgres (Neon or Supabase free tier) so multi-user state survives restarts.
   - Auth: magic-link/email so memory and plans persist per user.
   - Cost control: per-user rate limits + call caps; keep mock-LLM fallback as the floor.
   - Frontend: Streamlit is fine for this first deploy, but verify it is at least usable on mobile.
3. **Instrument analytics from day one** (PostHog or Plausible). Track: request completed, plan generated, thumbs up/down, return visit. Define "useful" as retention + completion, not visits.
4. **Soft launch** to the niche: Show HN, r/MealPrepSunday, r/fitness, macro-tracking communities — led by the benchmark story, with the live demo linked.

### Testing / evaluation gates
- Benchmark harness runs clean end-to-end from a fresh clone.
- Load-test the deploy at modest concurrency; confirm rate limiting works.
- Analytics events verified firing in production.

### Exit criterion
Live URL + published benchmark + analytics flowing. **You are now collecting real user signal while you build Phases 3–4.**

---

## Phase 3 — Differentiation Features (≈3–4 weeks)

**Goal:** Ship the features generic chatbots and recipe apps can't do, aimed at the macro-tracking niche.

### Tasks
1. **"Remaining macros" mode (reverse-macro solving).** Input: "780 kcal, 52 g protein, 40 g carbs left today" + pantry → closest-fit meal. Later: import remainders from MyFitnessPal / Cronometer / MacroFactor exports. This matches the *actual* daily workflow of macro-trackers.
2. **Deterministic substitution engine.** Curated substitution graph (Greek yogurt ↔ sour cream; allergen-safe swaps like sunflower-seed butter for peanut butter) with macro deltas computed from the nutrition DB. Substitutions are exactly where LLMs smuggle allergens back in — keep it deterministic, and extend the safety benchmark to cover substitution attacks.
3. **Visible personalization loop.** Make the existing thumbs feedback + memory *demonstrably* change future output: learned taste profile shown in the UI, auto-avoided ingredients, drifting cuisine preferences. Memory only matters if users can feel it.
4. **Cost estimation (v1).** Rough ingredient-price table → "this meal: ~$4.10; this week's list: ~$34, $12 already in your pantry."

### Testing / evaluation gates
- Remaining-macros solver: fit-error metric (kcal/protein deviation) evaluated over a test set; set a tolerance target (e.g., within 10%).
- Substitution engine: extend adversarial suite; allergy-violation rate must remain 0.
- A/B or before/after on personalization: does thumbs feedback measurably shift recommendations?

### Exit criterion
A macro-tracker can solve their "7pm remainder" problem end-to-end, safely, with visible personalization.

---

## Phase 4 — Retention & Planning Systems (≈4–6 weeks)

**Goal:** Move from one-shot answers to recurring weekly use — where real usefulness and retention live.

### Tasks (in order)
1. **Meal-prep batch solver first.** "Pick 2–3 recipes sharing ingredients, scale to 10 containers, each hitting X kcal / Y g protein, one consolidated shopping list." Smaller optimization problem than a full week, maps to real meal-prep-Sunday behavior, exercises the per-serving scaling work.
2. **Full weekly meal-plan solver.** Pantry + budget + macro goals + N meals → plan that maximizes pantry utilization, shares ingredients across meals, sequences perishables first, outputs one shopping list with estimated cost. This is the constrained-optimization destination both reviews converge on.
3. **Expiry / waste tracking.** Users log rough purchase dates for perishables; system nudges "use your spinach today — 3 ways." Recurring-use hook + quantifiable money/waste saved.
4. **Shareable plan URLs.** Every generated plan/recipe gets a public share link — free distribution and a measurable engagement signal.

### Testing / evaluation gates
- Solver correctness: shopping list quantities reconcile exactly against plan requirements minus pantry (quantity-aware from Phase 1 makes this checkable).
- Waste metric: % of pantry perishables consumed within the plan window.
- Retention: week-2 return rate for users who generated a weekly plan vs. one-shot users.

### Exit criterion
A user can run their whole week through MacroChef and come back next Sunday.

---

## Phase 5 — Ship the Final Product & Platform Play (ongoing)

**Goal:** Polish for scale, and open the engine to developers.

### Tasks
1. **Mobile-quality frontend.** Replace/augment Streamlit with a mobile-friendly web frontend (people cook on phones). Prioritize based on Phase 2–4 analytics showing mobile share.
2. **Expose the constraint engine as an API and/or MCP server.** "Food-safety filtering + macro scoring tools for AI agents" — repositions the project as safety infrastructure for food AI, and MCP servers get real developer attention right now.
3. **Vision, done properly (optional).** If Phase 2–4 data shows demand, implement one real vision provider with validated structured output and promote it back to a headline feature. **Pre-requisite before enabling any real provider:** replace the current silent mock-fallback in `app/services/model_provider.py` (`extract_inventory_with_provider_chain`) with explicit, user-visible degradation — tell the user that extraction failed and the result is mock, rather than quietly substituting canned data for a failed call.
4. **Launch v2** with the planner + benchmark + niche testimonials: Show HN follow-up, blog post on the solver design, dataset/benchmark release.

### Ongoing evaluation
- North-star metrics: weekly active planners, week-over-week retention, plans shared, benchmark still at 0 violations on every release (add to CI).
- Cost per user (LLM spend) tracked against rate limits.

---

## Dependency map (why this order)

```
Phase 0 (credibility)
   └─► Phase 1: nutrition DB + quantities + corpus   ◄─ blocking prerequisite for everything below
          ├─► Phase 2: benchmark + deploy + analytics ◄─ go live HERE, not at the end
          │        └─► real user signal feeds all later prioritization
          ├─► Phase 3: remaining-macros, substitutions, cost, personalization
          │        └─► Phase 4: batch solver → weekly planner → waste tracking → share links
          └─────────────► Phase 5: mobile frontend, API/MCP, vision, v2 launch
```

## Quick reference — which idea came from where

| Idea | Source |
|---|---|
| Weekly plan solver (waste/cost), USDA grounding, corpus scaling, expiry tracking, cost estimate, visible personalization, vision fix-or-reframe, Postgres/auth/analytics/hosting, mobile caveat | Opus 4.8 |
| Quantity/unit-aware inventory as blocking prerequisite, published safety benchmark, remaining-macros mode, meal-prep batch solver, substitution engine, API/MCP server, niche distribution + shareable plans, "deploy after Phase 2 not at the end" sequencing | Fable 5 |
| Product thesis, README/screenshot fixes, rate limiting, retention-based definition of "useful" | Both |
