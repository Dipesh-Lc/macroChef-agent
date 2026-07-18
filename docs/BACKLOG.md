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

### From the 2026-07-17 vocabulary consult (advisor ADVISE on soy-sauce/
### rennet-cheese/gelatin; entries required by that verdict)

- **URGENT, allergen-class: bare cheese-name rows invisible to `_DAIRY`.**
  Corpus rows a milk-allergic user can be served TODAY because no dairy
  alias substring-matches them: `gorgonzola` (2 rows), `gruyere` (2),
  `fontina` (1), `colby` (1), `queso fresco` (1). The `parmigiano` slice
  (1 row) was closed in the 2026-07-17 vocabulary pass (parmigiano/
  pecorino/grana padano/romano added to `_DAIRY`); the rest need a proper
  cheese-name audit of the corpus (FULL TREATMENT,
  `app/services/constraint_engine.py` `_DAIRY`). Zero over-block risk —
  these names are definitionally milk products.
- **Gorgonzola / gruyere PDO-verification cluster** (vegetarian
  exclusions): inclusion test pre-registered by the advisor — a cheese
  name enters `_RENNET_SET_CHEESES` iff its governing PDO/AOP standard
  MANDATES animal rennet (compliant product cannot be vegetarian).
  Gorgonzola DOP (2 corpus rows) and Gruyère AOP (7 rows) are plausible
  but unverified; manchego was REJECTED on the merits (its PDO permits
  non-animal coagulants). Verify the disciplinari, then add or reject
  with citations.
- **Grana Padano lysozyme → egg question**: the PDO also mandates
  lysozyme, an egg-derived enzyme. Separate from the rennet/vegetarian
  question — is "grana padano" an egg-allergen alias? Zero corpus rows
  today; decide with citations before it matters.
- **`_SOY` "tamari" substring over-match**: bidirectional matching makes
  the `tamari` alias wrongly block `tamarillos` (2 rows) and `tamarind
  pulp` (1 row) for soy-allergic users — water-chestnut-class wrong
  block (tamarillo is a fruit, tamarind a legume pod unrelated to soy).
  `_LOOKALIKE_EXCLUSIONS` candidate: `"tamari": {"tamarillo",
  "tamarillos", "tamarind"}`.
- **`SYNONYMS["gluten free tamari"] -> "soy sauce"` wart**
  (`app/utils/ingredient_normalizer.py`): normalization erases the
  affirmative GF label, so an explicitly gluten-free-labeled tamari row
  would fail closed under the new soy-sauce→wheat entry. Zero corpus
  occurrences, no benchmark case; fix only with a benchmark re-run per
  the frozen-normalizer rule below.
- **Condiment-wheat audit**: oyster sauce, ponzu, miso varieties — same
  hidden-wheat class as hoisin (9 rows, added) and teriyaki (0 rows,
  added). Measure corpus counts first, then decide per-term with
  citations; rejected as scope creep in the 2026-07-17 pass.
- **Gelatin-as-fish UX labeling** (non-blocking): "Contains: fish" on a
  gelatin dessert will confuse users. A label-explanation improvement
  ("gelatin — possible fish source, fail-closed") when label UX is next
  touched.

### Diet-path lookalike over-blocks after the tag-opt-out removal (diet_014
### remediation, `adjudication_20260718T090522Z.md`)

- **What happened:** removing `constraint_engine.violates_diet_type`'s
  diet-tag opt-out (the `requested in recipe_tags -> return False`
  early-return, deleted engine-wide per the diet_014 remediation) means
  every tagged recipe is now scanned unconditionally through
  `contains_allergen`/`_recipe_contains_any_term`, which is a substring
  match with no lookalike carve-out for these four terms. Four seed rows
  are now over-blocked for diets they are actually compatible with:
  1. `dairy-free` + term `milk` vs `ingredient:coconut milk` on r_007
     ("Indian Chickpea Spinach Curry") — coconut milk contains no dairy
     milk (FDA; also the `multi_018`/`multi_022` adjudicated-FP ruling for
     the ALLERGY path on this exact row).
  2. `dairy-free` + term `milk` vs `ingredient:coconut milk` on r_019 —
     same artifact, different seed row.
  3. `dairy-free` + term `butter` vs `ingredient:peanut butter` on r_002
     ("Thai Peanut Tofu Stir Fry") — peanut butter contains no dairy
     butter.
  4. `gluten-free` + term `flour` vs an `almond flour`-class ingredient —
     almond flour/meal contains no gluten (this is also why r_010's
     `almond flour` row was renamed to `almond meal` in the diet_014
     remediation itself, which sidesteps the artifact for that ONE row
     only by removing the trigger substring; any OTHER corpus row still
     literally named "almond flour" remains over-blocked for
     `gluten-free`).
  5. `vegan` + term `milk` vs `ingredient:coconut milk` on r_007 — same
     coconut-milk artifact as (1), on the vegan path (vegan exclusions
     include the full dairy alias set).
- **Availability cost:** r_002, r_007, and r_019 are unservable under the
  diets listed above even though they are genuinely compatible with them —
  a real, measured regression in recommendation availability for
  dairy-free/gluten-free/vegan users on those specific seeds, traded for
  closing the diet_014 admit-side gap.
- **Why not fixed now:** the obvious fix is a `_LOOKALIKE_EXCLUSIONS` entry
  for `milk` -> `{"coconut milk"}`, `butter` -> `{"peanut butter"}`, and
  `flour` -> `{"almond flour", "almond meal"}` (or similar), mirroring the
  existing `chestnut`/`romano` pattern. **This is explicitly out of scope
  for the diet_014 remediation** — `_LOOKALIKE_EXCLUSIONS` is consumed by
  `_is_lookalike_match`, which `_recipe_contains_any_term` calls
  unconditionally for BOTH the diet-exclusion path and `contains_allergen`
  (the shared allergy-safety path). Any lookalike entry added for `milk`,
  `butter`, or `flour` would also suppress those terms for a genuine milk,
  dairy-butter, or wheat-flour ALLERGY, not just the diet paths that
  motivate it here — a strictly higher-stakes change than the diet-only
  over-block it would fix. That is its own FULL TREATMENT decision
  (advisor ADVISE + REVIEW, matching `constraint_engine.py`'s tier) and
  requires a fresh adversarial benchmark run before/after to confirm no
  allergy-path admit regressions, not a same-pass addition to this
  remediation.

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
- **AMENDED 2026-07-18 (diet_014 remediation, `adjudication_20260718T090522Z.md`):
  this entry's original subset justification is now FALSE and is kept only for
  history.** `_violates_requested_diet` (`app/services/recipe_validation_service.py`)
  no longer treats vegetarian/vegan as tag-only: `constraint_engine.violates_diet_type`'s
  tag opt-out (the `requested in recipe_tags -> return False` early-return) was
  deleted engine-wide (all four diet types: gluten-free, dairy-free, vegetarian,
  vegan) because diet_014 proved it let a falsely-tagged recipe (r_004, tagged
  "vegetarian", bare `parmesan` row) serve unfiltered. `_violates_requested_diet`
  now requires vegetarian/vegan candidates to BOTH carry the tag AND pass
  `constraint_engine.violates_diet_type`'s scan (`requested not in tags or
  violates_diet_type(recipe, requested)`) — tag alone can no longer admit. The
  admit-set-subset argument this entry originally made (service admits a strict
  subset of the engine's tagged-OR-clean set) no longer describes the code: the
  service now scans via the engine directly. **Residual scope, still tag-only and
  still open: `high-protein`** — a nutrition-content label with no engine-side
  exclusion vocabulary, so `requested not in tags` remains its only check
  (unrelated failure mode: a candidate could be mis-tagged "high-protein" with no
  deterministic macro check here; out of scope for diet_014).
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
  [Decided 2026-07-17 by the human (decision 4A): the external-model
  comparison arms (3 models x {naive, steelman}, k=3, ~$12.21 estimated)
  are DEFERRED until the adjudicated-zero gate is met — they answer a
  marketing question, and the roadmap's "0 vs X%" claim is unpublishable
  before the gate anyway. Re-raise the cost sheet when the MacroChef arm
  reaches adjudicated-true 0.]
- **Pre-registered and not to be renegotiated after seeing a score**:
  release-blocking violation rate covers **`inherent` cases only**;
  `precautionary` (46 cases) is a separate non-blocking number. Current
  split: 259 inherent / 46 precautionary / 66 non-violation (60
  safe_control + 6 morphology no_claim). [Corrected 2026-07-17: the
  previous 262/49/60 figures were a transcription error against the
  immutable frozen case files (verified by direct count of
  `app/evaluation/benchmark/cases/*.jsonl`); runner denominators were
  always 259/46/60 -- see any benchmark report. Not a renegotiation.]
  [Gate-semantics amendment, 2026-07-17, decided by the HUMAN (the
  pre-registration was agent-authored, so agents could not amend it and
  may not revise this further): the release gate is **zero
  adjudicated-true inherent violations**. Every judge flag receives a
  written, advisor-reviewed per-case adjudication (convention:
  `data/evaluation/adjudication_20260717T145539Z.md`); judge-flagged and
  adjudicated-true are always published as a pair ("judge-flagged N/259;
  adjudicated true M/259"); judge FPs stay in the raw number forever; the
  judge is never modified to close the gap. Full text in CLAUDE.md
  "Honest scope".]

### Recorded 2026-07-17 (advisor REVISE on b9e663c+14f1cf0: items claimed
### "backlogged" in those commit messages but never written here; now written)

- **caramel + margarine absent from the dairy alias set**
  (`app/services/constraint_engine.py`, `_DAIRY` near the top of the
  file). Causes the hidden_002 ("Baked Caramel Corn" served to a
  milk-allergic user — its caramel is made FROM margarine) and hidden_004
  ("Panettone" with a literal `reduced-calorie margarine` row)
  precautionary benchmark failures; also implicated in hidden_007 (dark
  chocolate / milkfat). Pre-decided: these are may-contain
  (precautionary) hazards — margarine commonly contains whey/milk solids
  but dairy-free margarines exist — so adding them over-blocks some safe
  recipes; the Worcestershire fail-closed precedent argues for adding
  anyway. Needs a corpus-evidence pass (how many rows use margarine?)
  before the FULL TREATMENT engine change. Unmasked (not introduced) by
  the b9e663c quarantine; both cases were previously served safe recipes
  by retrieval luck.
- **Pipeline-side quarantine sidecar can still clobber**:
  `scripts/quarantine_flagged_recipes.py` was fixed (merge by recipe_id,
  first-decision-wins, atomic write — commit 1a13108, tests in
  `tests/test_quarantine_flagged_recipes.py`), but
  `CorpusImportPipeline._write_quarantine_jsonl`
  (`app/services/corpus_import/pipeline.py`) still overwrites
  unconditionally at the same default path
  `data/processed/quarantined_recipes.jsonl`. A future full corpus
  re-import would clobber the 186-row audit record exactly the way the
  script once took it 177 -> 9. Pre-decided: port the same
  merge/atomic-write helpers (or extract them to a shared module) with
  the same first-decision-wins semantics.
- **Stale Chroma embeddings for quarantined recipe ids** — quarantined
  rows are filtered at `load_corpus()`/retrieval time, so they are
  unservable, but their embeddings still sit in the Chroma index.
  Hygiene, not safety. Pre-decided: delete-by-id pass or full reindex at
  the next scheduled index rebuild; do not rebuild solely for this.
- **`_LOOKALIKE_EXCLUSIONS` structural invariant test**
  (`app/services/constraint_engine.py`, table near line 382): a
  malformed future entry (e.g. a lookalike phrase that does not strictly
  contain its key term, like `"chestnut": {"chest"}`) would silently
  suppress ALL matches for that allergen term. Pre-decided (advisor
  spec): ~10-line test asserting, for every entry, each lookalike phrase
  strictly contains its key (`term in phrase and phrase != term`) and
  the key exists in a base alias set. FULL TREATMENT process is the
  current guard.
- **`_is_lookalike_match` reverse-direction scope**: it also suppresses
  `recipe_term in term` matches, which the lookalike rationale doesn't
  cover. Advisor probed and found no live gap (bare "nut"/"nuts"
  ingredients still block via other aliases), but scoping to the forward
  direction only (`term in recipe_term`) would make semantics match the
  docstring. Same file, same FULL TREATMENT bar.
- **Lookalike carve-out is phrasing-dependent**: a user allergy typed as
  bare "nuts" still over-blocks water-chestnut recipes (exclusion is
  keyed on "chestnut(s)" only). Fail-closed, so cosmetic; note it in the
  table comment when next touching the file.
- **`_classify_match_rule` crash guard**
  (`scripts/run_safety_benchmark.py`): IndexError on a `matched_field`
  that is neither `title` nor `ingredient:...` — would crash the runner
  after the markdown report is written but before/while the evidence
  bundle lands. Defensive guard, one conditional.
- **Dirty-tree marker in benchmark report headers**: report
  `20260717T133000Z_derivative_quarantine.md` says "Git commit: b9e663c"
  but ran on a then-dirty tree. Add a `-dirty` suffix (via
  `git describe --dirty` or `git status --porcelain`) to the header for
  provenance honesty.
- **69c580f (unknown-diet_type fail-open fix): FULL TREATMENT review
  DONE 2026-07-17, VERDICT: APPROVED** (clean worktree at 69c580f).
  Fail-closed verified on every path — the diet partition is complete
  with ValueError on anything unrecognized, both services import the
  schema's sets (one definition, no drift), no caller bypasses, and the
  relaxation retry re-gates against the original request. Two
  non-blocking findings kept here: (1) `recipe_validation_node`
  (`app/graph/library_nodes.py`) lacks `discovery_node`'s try/except, so
  under llm/external/hybrid source modes an unknown diet_type surfaces
  as an unhandled exception (HTTP 500) — fail-closed but ungraceful;
  wrap it to a structured zero-candidate error. (2) Add a test pinning
  the relaxation path's downstream re-gating (relaxed candidates that
  violate the original diet must be rejected at validation).
- **Written per-case adjudication of judge flags** — DONE 2026-07-17:
  `data/evaluation/adjudication_20260717T145539Z.md` (19 inherent + 12
  precautionary flags, per-case verdict + citable rule, `_KNOWN_RESIDUALS`
  convention). Kept as a pointer because future runs must repeat the
  discipline: judge-flagged and adjudicated-true are ALWAYS reported as
  a pair, and the judge is never modified to close the gap between them.

### From the 2026-07-17 instructions-integrity spec (docs/instructions_integrity_spec.md)

- **Title-side bare-"fish"/meat-word checking remains an open residual.**
  The instructions-vs-ingredients check (spec above) reads `instructions`
  only, by design: bare-"fish"/meat-word TITLE checking is proven unsafe
  ("Fish Marinade", "Marinade for Beef" — legitimate intended-use titles
  that must not be blanket-quarantined), and in practice corrupt rows'
  instructions name the meat anyway, so instructions-side coverage
  catches the same rows. If a future corrupt row has a meat/fish title
  and instructions that never name the ingredient, neither check catches
  it; the benchmark + adjudication are the backstop. Any title-side
  extension needs the intended-use distinction designed first (see
  `adjudication_20260717T145539Z.md`, injection_014 "Needs").
- **Non-safety-vocabulary omissions are out of the check's scope** (the
  imp_f9cc221553155bfc orange-juice class): hidden non-allergen
  ingredients can't produce an engine-visible violation. Documented
  boundary, pinned by a must-NOT-flag test.

## Corpus / nutrition

- **Multi-source recipe variations pass (deferred from the 2026-07-18
  Food.com raw-scrape item).** The primary pass
  (`scripts/scrape_recipe_pages.py`) archives every corpus recipe's
  original Food.com page (exact match via the numeric RecipeId retained in
  `source_url`) to `data/scraped/foodcom/<id>.md` + `manifest.jsonl`. The
  user also wants the same recipes scraped from other reputable sites
  (AllRecipes, Serious Eats, BBC Good Food, …) as cross-checks/variations.
  Decided seam: a separate `scripts/scrape_recipe_variations.py`, separate
  `data/scraped/variations_manifest.jsonl`, output
  `data/scraped/variations/<foodcom_id>__<domain>.md` with frontmatter
  `matched_from_query`, `match_title`, `title_similarity` (rapidfuzz —
  already a dep), `match_confidence: high|medium|low`. Discovery via the
  DuckDuckGo HTML endpoint (no API key; brittle), parsing via
  `recipe-scrapers` (add the dependency only then). Priority input: ids
  whose latest primary-pass manifest status is `not_found` (dead Food.com
  pages — the variations pass is their only recovery; food.com /search/ is
  robots-disallowed, do not use it). Title-match ambiguity means a
  variation is stored, never merged silently — "most reliable source wins"
  resolution happens in the later structured-processing item, not at
  scrape time.
- **Process the raw scraped archive into the structured corpus.** The
  archive's JSON-LD `recipeIngredient` lines carry full amounts + units —
  this is the unblock path for the 2026-07-17 "units decision" (option 2A
  treated corpus recipes as discovery-only because units were missing).
  Later item: parse the fenced `Raw JSON-LD` block of each
  `data/scraped/foodcom/<id>.md` through
  `app/utils/quantity_parser.py`, re-derive allergen labels from the
  scraped ingredient names via `derive_allergen_labels`, and re-import.
  Quarantined recipes (1,354, also scraped) may be recoverable from
  original-page truth. FULL TREATMENT when it lands (touches allergen
  derivation inputs).
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
  fixture proves it. [Fixed 2026-07-17 as part of decision 2A below.]
- **Units decision — 2026-07-17, decided by the human (option 2A, "scope
  the claim honestly")**: corpus recipes are discovery/inspiration;
  quantity-aware features (pantry-match amounts, shopping-list math,
  Phase 3 cost estimation) are real only for the 25 hand-authored seeds
  and user-entered pantry items. The false adapters.py docstring is
  fixed and the limitation is stated in README "Limitations". Rejected:
  parsing units out of the instructions text (guessy, LLM-ish, feeds
  nutrition math — wrong units are worse than none) and an immediate
  corpus swap (Wikibooks already measured at 56/3,790 fully convertible,
  below its pre-registered import band). Consequence, stated plainly:
  **Phases 3 (cost estimation) and 4 (planner; its "shopping list
  quantities reconcile" test gate) remain blocked for the imported
  corpus** — becoming unblocked requires a unit-bearing corpus decision
  (re-raise Wikibooks or another CC0 source, license = human gate) as a
  Phase 3 prerequisite, not a quiet fix.
- Import parser range bug is fixed in `quantity_parser.py`, but
  already-imported rows keep old shapes until re-import.
- Regenerate `data/processed/grounding_report.md` end-to-end at the next
  change that alters any report NUMBER (two `_KNOWN_RESIDUALS` lines were
  text-synced by hand, verified byte-identical).
- **Retrieval-eval baseline regeneration after the 2026-07-18 mass
  quarantine.** The pinned baseline in `docs/phase-1.5-closeout.md` §4
  (67 queries, 4,263-recipe corpus, all-MiniLM-L6-v2) predates the
  instructions-integrity quarantine (imported corpus 4,045 → 2,889;
  human decision Option A, 2026-07-18). Re-run
  `python scripts/evaluate_retrieval.py` against the reduced corpus and
  re-pin; until then the old numbers stand as the Phase 3.5 fine-tune
  baseline for the corpus they measured, annotated non-comparable.
  Ground-truth relevant-set sizes will shrink (some pinned queries may
  need re-verification against the non-vacuity rule). Not
  ship-blocking.
- **Instructions-integrity residual classes (post-Option-A).** Recorded
  in `data/evaluation/instructions_integrity_report_20260718T001212Z.md`
  ("Residuals") and the two sample-audit records: (1) named
  variation-block headers ("San Francisco:") — rare multi-variation
  recipes, no deterministic rule separates them from genuine
  sub-component headers; (2) core-leniency non-flags where a listed
  same-category row satisfies any mention (imp_3aee17154e8c59e9's flour
  row vs its unlisted crust; imp_4e524f5f9f8759a9's soy-sauce row
  satisfying a bread-crumbs mention via dual-category membership — a
  candidate future ruling: dual-category terms satisfy only their own
  occurrences); (3) accepted FP imp_712db6319e3957c7 (non-contiguous
  intended-use phrasing); (4) measured ~10% FP rate among the 1,156
  quarantined rows — lost-recipe cost accepted by the human with
  Option A, restorable per-row via the sidecar if ever needed.

## Deploy / infra

- **Auth decision — 2026-07-17, decided by the human (option 3A, "accept
  and document")**: anonymous signed per-browser sessions ship instead of
  the roadmap Phase 2 "magic-link/email" exit criterion — an accepted
  deviation, not an oversight. Isolation is real and tested (forged/
  tampered/expired/attacker-signed tokens all 401); the tradeoffs
  (cookie clear or device switch = fresh library; 30-day token expiry
  orphans the old library) are documented in README "Limitations".
  Rationale: magic-link adds an email-provider human gate + PII to a
  hobby demo with no users yet, and reopens the HttpOnly deviation the
  advisor accepted specifically because scope is anonymous. Honest
  residual: **Phase 4's retention metrics ("week-2 return rate")
  genuinely need durable identity** — build magic-link when retention
  measurement actually starts, not before.
- **Deploy cost — 2026-07-17, money gate RESOLVED: approved by the human
  (option 4A)**: `min_replicas=1`/`max_replicas=1` at ~$15–30/month
  accepted (single-writer embedded Chroma pins the replica count; see
  docs/DEPLOY.md). Scale-to-zero rejected (3.42GB torch image, 30–60s
  cold start on a benchmark-led launch); external vector store stays
  backlogged below. The production deploy itself remains a separate
  "Public actions" human gate.
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
