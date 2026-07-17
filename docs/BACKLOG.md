# BACKLOG.md

Destination for everything the "Default to backlog" rule in `CLAUDE.md`
sends here: eval-methodology polish, report wording, citation
verbatim-ness, docstring-accuracy passes, corpus quality work, and any
"noticed, not fixed" item from an executor/mechanic report that isn't
required to ship.

**The rule this backlog exists to enforce:** "refine later" means never
unless it is written down here. Every entry below must carry enough context
that someone could act on it cold — file paths, what was already decided,
and any pre-registered criteria. Do not re-derive from a vague note; if an
entry here is under-specified, that's a bug in the entry, not license to
guess.

When you add to this file, match the existing entry style: what/where,
what's already decided, and (if applicable) the exact numeric criteria that
were pre-registered before anyone saw a result.

---

## Safety-adjacent (frozen pending the adversarial benchmark)

- **`ingredient_matches` raw-substring bug** — `app/utils/ingredient_normalizer.py`.
  `left in right or right in left` plus a fuzzy fallback. Consumers:
  `app/services/recipe_discovery_service.py` (`_allowed`/`_has_conflict`),
  `procurement_service.py`, `recipe_validation_service.py`. **Any fix MUST
  re-run the full adversarial benchmark first.**
- **`recipe_discovery_service._allowed` bypasses `constraint_engine`** —
  calls `_has_conflict` directly against `ingredient_matches`, which does
  not expand `ALLERGEN_ALIASES` (won't know "casein" implies dairy).
  Currently over-blocks rather than under-blocks (every candidate still
  passes `constraint_engine` downstream), but it re-implements a safety
  check the engine owns.
- **THREE protections rest on the frozen normalizer's behaviour** — a
  rewrite silently removes them, and they are not obvious from the code:
  1. `"prawns"` -> `"shrimp"` via SYNONYMS is what makes plural prawn block.
  2. groundnut oil blocks under a `nuts` allergy only via `"nuts"` ->
     `"nut"` singularization.
  3. `"tree nuts"` (a free-text label real users type) works only via
     depluralization.

  Each is now backed by an explicit alias entry or a benchmark case, but
  **re-verify all three before touching the normalizer**.
- **Pre-existing over-blocks, deliberately kept**: `eggplant` trips `egg`;
  `buckwheat` trips `wheat`. Same substring root cause. Wanted as benchmark
  safe-controls (`safe_025`, `safe_050`, `morphology_015`, `morphology_034`).
- **`crustacean` + "shellfish stock"** — was SERVED, now blocked; the wider
  parallel-set audit is done, but re-check if new alias keys are added.
- **Unknown `diet_type` fails OPEN in `_violates_requested_diet`** —
  `app/services/recipe_validation_service.py`, final `return False` (~line 152).
  The function returns `False` (ADMIT, no violation) for any diet type it doesn't
  recognize. `RecipeDiscoveryRequest.diet_type` (`app/schemas/library.py`) is
  freeform `str | None`, so an API caller sending e.g. `diet_type="nut-free"`
  silently gets ZERO diet filtering. **PRE-EXISTING, not from commit 61e03f8.**
  Low severity today: FastAPI binds `127.0.0.1:8000` (internal only, verified in
  container) and Streamlit dropdown enforces values. API-reachable only, not exposed.
  **If the API gains public ingress, this becomes live and must be fixed first.**
  Fix shape (already decided): constrain `RecipeDiscoveryRequest.diet_type` to
  validated set (like `UserProfile.diet_type` does in `app/schemas/user.py:35-41`),
  OR mirror `constraint_engine.violates_diet_type`'s fail-loud `ValueError` — the
  engine's comment reads "Returning False would silently claim the recipe is safe...
  fail loudly instead". Engine defends; discovery-request path has neither defense.
- **Vegetarian/vegan/high-protein remain tag-only in `_violates_requested_diet`** —
  same file and function. Those three diets are decided by tag presence
  (`requested not in tags`) rather than through the constraint engine. Explicitly
  scoped out of commit 61e03f8. Advisor analysis: admit set is strict SUBSET of
  engine's (`violates_diet_type` admits tagged OR ingredient-clean; service admits
  tagged only), so it fails CLOSED for untagged recipes — over-blocking, the safe
  direction. Residual risk is falsely-tagged recipes, pre-existing in `constraint_engine
  .violates_diet_type`'s own tag opt-out (including LLM-authored `diet_tags` on
  `ai_generated` candidates). Entry recorded here because commit message is not the
  backlog: per CLAUDE.md, "refine later" means never unless written down.
- **`/inventory/extract`: add auth + rate limit BEFORE enabling vision** —
  `app/api/routes_inventory.py`, `POST /inventory/extract`. The route currently
  takes NO session dependency and has NO rate limit. NOT a live hole: `MACROCHEF_ENABLE_VISION`
  defaults to `False` (checked at `app/config.py:82`), so the image path returns
  403 before any paid vision call. The text path uses only `re`, the ingredient
  normalizer, and the quantity parser — fully deterministic, no LLM. The API is
  loopback-only in the deployed container. **Trigger — if `MACROCHEF_ENABLE_VISION`
  is ever enabled, this route instantly becomes an unauthenticated, unlimited,
  paid-vision-call and disk-write endpoint. Add a session dependency
  (`Depends(get_session_user)`) and a rate-limit bucket BEFORE enabling vision** —
  not "revisit later". For reference, discover/recommend are 20/hr and reindex is 2/hr.

## Safety benchmark (case set is FROZEN at 371; everything downstream deferred)

- Independent judge (`app/evaluation/benchmark/safety_judge.py`) with an
  **enforced import ban** on `ingredient_normalizer`/`constraint_engine`,
  tested by walking the import graph.
- **`scripts/run_safety_benchmark.py` does not exist yet** — `app/evaluation/benchmark/`
  currently has `case_schema.py`, `loader.py`, and the frozen `cases/` directory, but
  no runner. Building the runner and executing all 371 cases against a paid API is a
  money gate requiring human cost approval.
- Harness specification (future): arms = MacroChef(mock),
  MacroChef(real, gated), 3 models x {naive, steelman}; both execution
  surfaces; structured-JSON contract; response cache; `non_answer` category.
- First MacroChef run + gap triage (any violation = stop-the-line, disclosed
  with commit refs).
- **Mutation self-check** — plant a fault, confirm the benchmark goes
  nonzero. A safety net that never caught a planted fault is unproven.
- Stats: k=3 runs, Wilson 95% CI, any-run worst case; pinned model snapshot
  ids; dated tables.
- Cost sheet -> human gate. CI gate on the MacroChef arm only.
- **Pre-registered and not to be renegotiated after seeing a score**:
  release-blocking violation rate covers **`inherent` cases only**;
  `precautionary` (46 cases) is a separate non-blocking number. Current
  split: 259 inherent / 46 precautionary / 66 non-violation (60
  safe_control + 6 morphology no_claim). [Corrected 2026-07-17: the
  previous 262/49/60 figures were a transcription error against the
  immutable frozen case files (verified by direct count of
  `app/evaluation/benchmark/cases/*.jsonl`); runner denominators were
  always 259/46/60 -- see any benchmark report. Not a renegotiation.]

## Corpus / nutrition

- **Wikibooks import** — human already cleared CC BY-SA 4.0 for
  measurement; split-licensing decided (MIT code, CC BY-SA data).
  **Pre-registered import bands, set before the number existed: >=750
  fully-convertible recipes -> import; 300-750 -> human decides; <300 -> do
  not import.** Measured baseline: **56 / 3,790 (1.48%)**.
- **Conversion surface is the real blocker, not the corpus.**
  `app/utils/unit_converter.py` has a 12-entry density table and 10-entry
  piece-weight table; 12,390 of 33,286 Wikibooks occurrences (37%) have a
  *recognized* unit that `to_grams` still can't convert (cup 4,440, tsp
  3,921, tbsp 3,088). Advisor ruling on the fix is preserved: a **private
  nutrition-path-only** `_normalize_for_density_lookup()` inside
  `unit_converter.py`, **exact-match only** (no fuzzy/substring),
  **strict-first then legacy fallback**; strip handling words
  (chopped/diced/sliced) but **NEVER composition or physical form**
  (almond/brown/heavy/granulated/powdered/cooked -> those become explicit
  multi-word keys); **every entry needs a cited reference weight** — no
  LLM-recalled densities; no can/package/bunch.
- **Latent bug found, not fixed**: the legacy path strips `"cooked"` via
  `DESCRIPTORS`, so `"1 cup cooked rice"` hits the *uncooked* density
  (~15% error). The strict-first ordering fixes it as a side effect.
- **The imported Food.com corpus has no units** — 35,059 of 35,183
  ingredient rows are `unit: None`, so corpus-wide GROUNDED is structurally
  ~0% and 89% of rows land in the report's `no_unit` bucket. LLM unit
  inference and default-unit tables were both **considered and rejected**
  (the first violates the safety invariant; the second fabricates up to
  ~20x error).
- `app/services/corpus_import/adapters.py` docstring still claims Food.com
  embeds units in ingredient text — **false for the entire dataset**; the
  fixture proves it.
- Import parser range bug is fixed in `quantity_parser.py`, but
  already-imported rows keep old shapes until re-import.
- Regenerate `data/processed/grounding_report.md` end-to-end at the next
  change that alters any report NUMBER (two `_KNOWN_RESIDUALS` lines were
  text-synced by hand, verified byte-identical).

## Deploy / infra

- Alembic (currently `create_all` only — never alters existing tables).
- Multi-replica / external vector store (embedded Chroma is single-writer
  -> `min_replicas=1`). **The in-memory rate limiter
  (`app/services/rate_limiter.py`, wired in `app/dependencies.py` for
  `/library/discover`, `/recipes/recommend`, `/library/reindex`) shares this
  exact assumption**: counts live in one process's memory, so they are
  correct only because `min-replicas=1`/`max-replicas=1` is pinned. If
  replicas ever go above 1, the limiter silently becomes per-replica (a user
  could get up to `limit * replica_count` requests with no error) — this
  must move to a shared store (e.g. Redis) in the same change that lifts
  the replica pin, not as an afterthought.
- **`/library/reindex` rate limit is per-session, not global** — it caps
  each individual verified session to `RATE_LIMIT_REINDEX_MAX` (default 2)
  calls per `RATE_LIMIT_REINDEX_WINDOW_SECONDS` (default 3600s), same as
  `/library/discover` and `/recipes/recommend`. But reindex rebuilds one
  *shared* corpus index, not anything scoped to the caller, so many distinct
  anonymous sessions (trivial to mint — no login) could still each spend
  their own small quota against this expensive synchronous endpoint, adding
  up to more load than the per-session cap alone suggests. A global
  (all-sessions) cap in addition to the per-session one was considered and
  deliberately deferred — flagged for the advisor review this task requires,
  not decided unilaterally here.
- Magic-link auth via an email provider (anonymous signed session cookie
  ships first).
- `extract_inventory_with_provider_chain` ends in an unconditional `return
  mock_extractor(...)` — if every real provider errors, users get canned
  fake inventory with no signal. `TODO(Phase 5)` acknowledges it. Vision is
  off by default (`MACROCHEF_ENABLE_VISION=false`).
- `app/main.py` uses deprecated `@app.on_event("startup")`.
- 5 orphaned Chroma HNSW segment dirs (~7.5 MB each) from past rebuilds.
- Blog post, HF dataset publication, launch drafts (all human gates).

## Post-deploy, non-blocking (from 875f716 pre-deploy review)

- **Promote `_serializer` to a public helper.** `frontend/session_client.py` imports
  the private `app.dependencies._serializer` to validate tokens locally before use.
  Advisor judged this CORRECT — the alternative (frontend re-implementing salt +
  `max_age`) is exactly the silent-drift class this work exists to kill, and the
  import fails loudly at module load if the name disappears. Follow-up is cosmetic:
  expose `token_is_locally_valid(token) -> bool` in `app/dependencies.py` so the
  contract is named rather than borrowed.
- **`.strip()` the resolved secret.** `app/dependencies.py:87`'s `if secret:` accepts
  a whitespace-only `SESSION_SECRET=" "` as a real secret. Human-set value only,
  not reachable by config drift — negligible, but trivially fixable.
- **Consolidate duplicate tag rendering.** `frontend/components/recommendation_cards.py:43-44`
  keeps a private `_tags` that duplicates `html_safe.tag_row_html`. Both escape
  correctly today; this is de-duplication only, not a fix.
- **Comment `UserProfile.user_id` as inert.** `app/schemas/user.py` — it defaults
  to "demo_user" and is client-supplied, but is never used for scoping or authorization
  (verified: `grep -rn "user_profile.user_id\|profile.user_id" app/` returns nothing).
  Add a comment saying it is NOT a trust boundary, so a future engineer doesn't
  mistake it for one.
- **`RateLimiter._hits` never evicts keys.** `app/services/rate_limiter.py` —
  unbounded slow memory growth across anonymous sessions. Fine for the pinned
  single-replica topology with restarts; note it alongside the existing single-replica
  entry in the Deploy / infra section rather than as a separate concern.
