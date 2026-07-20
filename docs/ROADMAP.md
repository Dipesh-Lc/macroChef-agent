# MacroChef Agent — Consolidated Upgrade & Launch Roadmap

Merged plan from both reviews (Opus 4.8 + Fable 5). Organized so each phase has a clear goal, tasks, testing/evaluation gates, and an exit criterion. Sequenced so you deploy publicly at the end of Phase 2 — not at the very end — and iterate on real user signal.

**Product thesis (agreed by both models):** MacroChef is not "a recipe LLM." It is a *deterministic meal-planning and food-safety engine* that uses an LLM only for the fuzzy parts. Every phase below either proves that thesis, deepens it, or distributes it.

**Target audience (pick a niche, don't build for "everyone with a fridge"):** macro-trackers, lifters, meal-preppers, cut-phase dieters. The name macroChef already speaks to them.

---

## Status snapshot (2026-07-19)

| Phase | Status |
|---|---|
| 0 — Credibility | **DONE**, except README screenshots + demo GIF (human gate). |
| 1 — Trust & grounding | **DONE** (USDA grounding, quantity model, 4,238-recipe corpus, re-derived macros). Residuals tracked in `docs/BACKLOG.md` "Corpus / nutrition". |
| 2 — Benchmark + deploy | **Live** at ca-macrochef (italynorth) since 2026-07-18. MacroChef arm run, gate met: judge-flagged 17/259, adjudicated-true **0/259** inherent. NOT done: external-model comparison arms (money gate ~$12), analytics verified firing in prod (human), soft launch (human), screenshots (human). |
| 3 — Differentiation | Not started (B1–B5 not yet begun). Was blocked by the unitless corpus — unblocked 2026-07-18 by the Food.com raw-page scrape; the corpus itself re-imported from that scrape **2026-07-19 (task A1)**: unit coverage 0.35% → **76.14%** (30,780/40,423 ingredient rows), imported corpus now 3,853 active / 379 quarantined (after the diet_023 safety-benchmark cure round, see docs/BACKLOG.md). A2 (widen the conversion surface) already landed at commit `6482c6b`, ahead of A1. A3 (re-ground nutrition corpus-wide) has not run against the new corpus yet — the unlock chain (A1→A2→A3) is otherwise clear for B1–B5 to start. |
| 4 — Retention/planning | Not started. Same blocker, same unblock as Phase 3. |
| 5 — Platform | Not started. |

The forward plan below ("Unlock chain") supersedes the Phase 3–4 internal ordering where they differ; the phase texts remain as reference. Known stale docs: `frontend/streamlit_app.py` disclaimer still says the benchmark "has not yet been run" (fix in C0 below); `docs/BACKLOG.md:195` says the benchmark runner doesn't exist (it does).

---

## Forward plan (added 2026-07-19): unlock chain → features → frontend

### Stage A — The unlock chain (backend; do this before any UI work)

Everything below depends on this chain — precise macros only exist once
ingredients convert to grams.

- **A1. Process the scraped archive into the structured corpus — DONE
  2026-07-19** (FULL TREATMENT, two advisor REVISE rounds before landing;
  touched allergen-label derivation AND `constraint_engine.py` vocabulary
  by the second revise round). `FoodComScrapedArchiveAdapter`
  (`app/services/corpus_import/adapters.py`) reads
  `data/scraped/foodcom/*.md` (the fenced `Raw JSON-LD` block), ingredient
  lines through `parse_quantity_string`, allergens re-derived via
  `derive_allergen_labels`, `recipeYield` → `servings`,
  `recipeCategory` → `meal_type`, through the existing pipeline
  (validation → dedup → integrity quarantine → rewrite
  `imported_recipes.jsonl` → reindex). **Result: unit coverage 0.35% →
  76.14%** (30,780/40,423 rows); corpus 3,853 active / 379 quarantined
  (after the diet_023 cure round) (984 of the original 1,354 quarantined
  rows recovered from original-page truth, 5 newly quarantined by the
  automated checks, 3 ids permanently lost to persistent HTTP 500, plus 6
  more manually quarantined during the diet_023 cure round below). Along
  the way this also fixed real, pre-existing `constraint_engine.py`
  vocabulary gaps (`bratwurst`/`bologna`/`sirloin` in `MEAT_ALIASES`,
  `pretzel`/`pita`/`orzo` in `_WHEAT`, `yoghurt`/`curd` in `_DAIRY`,
  `bean curd` in `_SOY`, and — via a real adjudicated benchmark
  TRUE_VIOLATION, "krispies"/"cereal" in the gluten composition and
  "enchilada sauce" in `_PEANUT`) that the richer scraped-page ingredient
  text exposed via `tests/test_diet_leak_audit.py` and the adversarial
  safety benchmark (previously green/passing only because the old CSV's
  truncated ingredient columns hid the very ingredients that would have
  tripped them — see `docs/BACKLOG.md`'s A1 entries for the full
  root-cause writeup, the per-term over-block deltas, and the FULL
  TREATMENT items left behind: `derive_allergen_labels` natural-language
  robustness, a systematic ground-truth-vs-production vocabulary diff,
  and a direction-aware lookalike matching mechanism).
  *Eval gate, all met:* pytest green (977+ tests) + `evaluate_demo_set.py`
  at 0.000 + Chroma reindex (3,878 == 3,878 active+seed lines, final cured corpus) +
  safety-benchmark MacroChef arm re-run + `evaluate_retrieval.py`
  re-baseline (non-comparable-to-prior note) + before/after unit coverage
  stat published in the import report and here.
- **A2. Widen the conversion surface.** `app/utils/unit_converter.py` has a
  12-entry density table and 10-entry piece-weight table — the real
  bottleneck. With units now present, every added entry (cup of flour,
  tbsp of oil…) converts hundreds of rows to grams. Per the standing
  advisor ruling (BACKLOG "Corpus / nutrition"): strict-first
  `_normalize_for_density_lookup()`, exact-match only, **every entry needs
  a cited reference weight** (USDA FoodData Central / King Arthur /
  peer-reviewed tables — no LLM-recalled densities), never strip
  composition/physical-form words. Also add the missing unit aliases
  (pinch/dash/quart/pint/gallon/fl oz/stick) to `quantity_parser.py`.
  Fixes the latent `"cooked"`-stripping density bug as a side effect.
  *Eval gate:* unit tests against the cited reference values; corpus-wide
  conversion-rate stat before/after.
- **A3. Re-ground nutrition corpus-wide — DONE 2026-07-20:** partial 85.8% /
  ungrounded 13.8% / kcal median abs relative error 16.1% (see
  `data/processed/grounding_report.md` and pre-A3 baseline
  `data/processed/grounding_report_pre_A3_baseline.md`). Corpus-wide
  grounding (3878 recipes) via `scripts/ground_corpus.py` (USDA FDC, cached,
  `FDC_API_KEY` already provisioned). Pre-A3 baseline was grounded 0.4% /
  partial 59.2% (on the pre-A1 4,263-recipe corpus); the current run is on
  the A1-rebuilt 3,878-recipe corpus with unit coverage 76.14%.

### Stage B — Features that make it actually useful (each ships with an eval)

- **B1. Per-serving macro cards with provenance.** Calories/P/C/F per
  serving plus a **grounding badge** (N of M ingredients USDA-matched vs
  estimated). Honest uncertainty display is good UX and on-brand; builds
  on the existing `nutrition_view.macro_display_state` trust chokepoint.
- **B2. Serving scaler.** 1–8 servings slider rescaling every ingredient
  amount and the macros live. Trivial once quantities are structured;
  feels magical.
- **B3. Macro-targeted day planning.** "Hit 2,200 kcal / 160 g protein" →
  the deterministic side assembles a day plan from grounded recipes
  summing to target within tolerance. Knapsack-style solver component —
  strong portfolio piece, stays deterministic (no safety-invariant
  issues). Absorbs Phase 3 item 1 ("remaining macros") and seeds the
  Phase 4 solvers. *Eval:* fit-error metric (kcal/protein deviation) on a
  test set, tolerance target pre-stated.
- **B4. Shopping-list aggregation across the plan.** Merge quantities
  across the week, normalized to sensible purchase units. Extends the
  existing `procurement_service.merge_shopping_lists` from per-recipe to
  per-plan. *Eval:* reconciliation test — list quantities equal plan
  requirements minus pantry, exactly (Phase 4 gate, now checkable).
- **B5. Pantry match by weight.** Rank recipes by fraction of ingredient
  **mass** covered, not name-count (upgrade `pantry_match_score` in
  `nutrition_scorer.py`; `to_grams` does the work).
- **B6. Recipe variations surface.** "Restored from source" badge for
  quarantined recipes recovered in A1; later, the multi-source variations
  pass (backlogged) gives side-by-side versions.

### Stage C — Frontend redesign

- **C0 (immediate, independent of A):** fix the stale benchmark disclaimer
  in `frontend/streamlit_app.py` — it must state both numbers
  (judge-flagged 17/259; adjudicated-true 0/259) per Honest scope. Do
  before screenshots.
- **C1. Two-pane layout:** conversational agent left, live **plan canvas**
  right (day/week grid, macro totals updating as recipes land). Recipe
  detail views with the scaler; macro donut per recipe; stacked daily
  totals against target bands.
- **C2. Make safety visible:** the allergy-filter status always on screen
  ("filtered deterministically: N recipes excluded for tree nuts") —
  turns the safety architecture into a visible feature.
- **C3. React frontend against the existing FastAPI** — only if Streamlit
  fights the two-pane design; bigger scope, itself a portfolio upgrade.
  **Human decision point before starting C3.**

### What makes it impressive to a reviewer (standing principles)

1. **The honesty layer** — grounded-vs-estimated data quality shown per
   recipe. Rare in the wild; demonstrates mature ML-product thinking.
2. **An eval for every new component** — e.g. macro-computation accuracy
   vs the 25 seed recipes as ground truth, published. Keeps the
   "no unevaluated components" discipline that distinguishes this repo.

### Execution order for everything still unimplemented

| # | Item | Tier | Depends on |
|---|---|---|---|
| 1 | A1 archive → corpus | FULL TREATMENT | scrape (done) |
| 2 | A2 conversion surface | FULL TREATMENT (advisor ruling applies) | — (parallel with A1) |
| 3 | A3 re-ground + seed-accuracy eval | EVERYTHING ELSE | A1, A2 |
| 4 | C0 stale-disclaimer fix | EVERYTHING ELSE | — (do first) |
| 5 | B1 macro cards + B2 scaler | EVERYTHING ELSE | A3 |
| 6 | B5 pantry-by-weight | EVERYTHING ELSE | A3 |
| 7 | B3 day-plan solver (+ eval) | FULL TREATMENT (serves plans → allergy surface) | A3 |
| 8 | B4 shopping aggregation (+ reconcile test) | EVERYTHING ELSE | B3 |
| 9 | C1+C2 frontend redesign | EVERYTHING ELSE (C2 wording advisor-checked) | B1–B4 |
| 10 | B6 variations surface | EVERYTHING ELSE | A1 |
| 11 | Phase 3: substitution engine | FULL TREATMENT (allergen swaps) | A3 |
| 12 | Phase 3: visible personalization; cost v1 | EVERYTHING ELSE | B1 |
| 13 | Phase 4: batch solver → weekly solver → expiry → share URLs | mixed (solvers FULL) | B3, B4 |
| 14 | Phase 5: API/MCP server, mobile polish, real vision, v2 launch | per-item | user signal |

Human gates unchanged and still open: screenshots/GIF, analytics
verification, soft-launch posting, external benchmark arms (~$12),
corpus-license posture for public deployment (A1 re-imports Food.com-
derived data into the served corpus — same posture question as today,
flag at A1 review), React-frontend scope call (C3).

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
