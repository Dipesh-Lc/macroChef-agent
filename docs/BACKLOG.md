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
- ~~`scripts/run_safety_benchmark.py` does not exist yet~~ **STALE — it
  exists and has been run** (MacroChef mock arm, 2026-07-18: judge-flagged
  17/259, adjudicated-true 0/259 inherent; gate met). Still open: the
  external-model comparison arms (3 models x {naive, steelman}) remain a
  money gate (~$12) requiring human cost approval + provider keys.
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
- **Pipeline-side quarantine sidecar can still clobber** — **DONE
  (atomicity) 2026-07-19, task A1.** `CorpusImportPipeline.
  _write_quarantine_jsonl` (`app/services/corpus_import/pipeline.py`) now
  writes atomically (temp file + `os.replace`, ported from
  `scripts/quarantine_flagged_recipes.py`'s `_write_quarantine_atomic`;
  test: `tests/test_corpus_import_quarantine.py::
  test_interrupted_quarantine_write_never_truncates_existing_sidecar`).
  Deliberately NOT a merge, unlike the original ask below: the A1 task
  spec decided a scraped-archive re-import is a NEW GENERATION that makes
  fresh decisions on every one of the 4,235 archive ids, full rewrite by
  design (`pipeline.run(..., dry_run=True)` + `pipeline.write(...)`). The
  original "silently overturn a human decision" risk this item was really
  about is now closed by a STRONGER, more targeted mechanism instead:
  `scripts/import_corpus.py`'s `_ADVISOR_APPROVED_MANUAL_RELEASES`
  allowlist + hard halt — any `quarantine_reason.check ==
  "manual_adjudication"` row that a re-import would release must be on
  that advisor-reviewed allowlist (with cited cure evidence) or the run
  halts before any corpus/sidecar write
  (`tests/test_import_corpus_scraped_archive_reimport.py`). Original ask,
  preserved for context: `scripts/quarantine_flagged_recipes.py` was fixed
  (merge by recipe_id, first-decision-wins, atomic write — commit
  1a13108, tests in `tests/test_quarantine_flagged_recipes.py`), but the
  pipeline's own writer still overwrote unconditionally at the same
  default path, and a future full corpus re-import would clobber the
  186-row audit record exactly the way the script once took it 177 -> 9.
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
- **Process the raw scraped archive into the structured corpus** — **DONE
  2026-07-19, task A1 (VERDICT: REVISE then landed).**
  `FoodComScrapedArchiveAdapter` (`app/services/corpus_import/adapters.py`)
  + `scripts/import_corpus.py --dataset foodcom_scraped_archive` re-import
  ran for real against all 4,235 archive files, wrote the new corpus
  (`imported_recipes.jsonl`: 3,857 active; `quarantined_recipes.jsonl`:
  375 quarantined), reindexed Chroma, and re-ran the full test suite +
  demo eval + safety benchmark. Unit coverage 0.35% -> 76.14% (the whole
  point of the migration). Full ledger/released/manual-adjudication
  artifacts under `data/processed/` and `data/processed/quarantine_history/`
  (run `20260719T070200Z`). See the two new entries directly below for the
  methodology gaps this exposed (both explicitly NOT fixed here —
  `constraint_engine.py`/`ingredient_normalizer.py` were off-limits for
  this task). Quarantined recipes WERE recoverable from original-page
  truth: 982/1,354 released (72.53%; non-gating for this source upgrade
  per advisor adjudication 2026-07-19 — 811 have the flagged term
  literally present in the scraped rows, 159 pass a fresh recheck via
  category vocabulary, 12 are pre-existing manual-adjudication
  quarantines individually cured at source, see
  `data/processed/quarantine_history/manual_release_adjudication_20260719T070200Z.md`).

- **FULL TREATMENT: `derive_allergen_labels` natural-language robustness —
  DONE 2026-07-20** (advisor-consulted design, executed this task; commit
  message prefix "A1 backlog / derive_allergen_labels substring-consistency
  + fish-allergen coverage fix"). `derive_allergen_labels`
  (`app/services/constraint_engine.py`) now reuses the exact same two
  primitives `contains_allergen` calls (`_expand_allergen_terms`,
  `_any_term_matches`), plus the same bare-nut-word compensation
  (`_ingredient_names_have_bare_nut_word`, mirroring
  `_recipe_has_bare_nut_word`), per candidate `ALLERGEN_ALIASES` key, instead
  of exact-set membership matching. **Verified corpus-wide (3,884 active
  recipes, 2026-07-20), not sampled:** (1) superset regression check: 0
  recipes lost a label versus the pre-fix exact-set baseline; (2) closed-loop
  invariant (`L in derive_allergen_labels(ingredient_names)` iff
  `contains_allergen(recipe, [L])`, isolated to ingredient-name-driven
  matching — see the discovered artifact note below): 0 violations across
  every recipe x every `ALLERGEN_ALIASES` key; (3) aggregate label-gain:
  2,779 recipes gained >=1 label, 0 recipes lost any label; (4) quarantine
  churn from `title_ingredient_integrity.py`/`instructions_ingredient_
  integrity.py` (both OR-arm against `recipe.allergens`): 0 newly flagged, 0
  newly released — no surprise, matches the fail-safe expectation; (5) one
  corpus-wide Chroma reindex run (`scripts/backfill_recipe_library.py` ->
  `RecipeIndexingService().rebuild_index_clean`): 3,884 indexed = 3,859
  active imported + 25 seed, parity confirmed; (6) `contains_allergen`
  itself: zero behavioral changes (only reused, never modified) — full
  pytest green, `evaluate_demo_set.py` allergy_violation_rate 0.000.
  **Discovered artifact (documented, not fixed, out of scope):** testing the
  closed-loop invariant against a recipe's LIVE, not-yet-backfilled
  `recipe.allergens` field (rather than isolating to ingredient names) surfaces
  34 (pre-fix) / 166 (post-fix, in-memory self-consistent backfill) apparent
  mismatches, all traced to one pre-existing, unrelated mechanism:
  `_recipe_safety_terms` unions ingredient names WITH `recipe.allergens`
  text, and the literal label string `"shellfish"` contains the substring
  `"fish"` — so any recipe whose *label* says "shellfish" trivially also
  satisfies a bare "fish" substring check via that label text alone,
  independent of real fish content. This is a separate, pre-existing
  property of `contains_allergen`/`_recipe_safety_terms` (present before this
  task, out of scope to touch per this task's hard constraints) — not a new
  gap. `data/processed/imported_recipes.jsonl`'s `allergens` field itself was
  deliberately NOT backfilled as part of this task (that's `scripts/
  backfill_allergen_labels.py`'s job, run historically as its own dedicated
  commit — see commit `06db836`) — a natural follow-up if the metadata-display
  benefit is wanted in the live served corpus; the Chroma index's
  `contains_<allergen>` boolean metadata flags already reflect the new
  derivation today regardless, since `recipe_indexing_service._recipe_
  allergen_terms` calls `derive_allergen_labels` live at index time.

  **Part B, folded into the same task — fish-species vocabulary sweep**
  (`_FISH` in `app/services/constraint_engine.py`): an advisor review of item
  2 (vocabulary gap closure, commit `d200acb`) claimed `_FISH` was missing
  `bass`/`sea bass` and that a real corpus recipe (`imp_aa6c99eae4fd5f58`,
  "Sea Bass in a Sesame Seaweed Spaetzle Crust", ingredient "filets of fresh
  sea bass") was under-blocked for fish allergy. **Factual correction,
  confirmed via `git log -p -S'"sea bass"'`:** `"sea bass"` has been a member
  of `_FISH` since commit `4bf2377` (2026-07-17) — before item 2 and before
  this task — and `contains_allergen(recipe, ["fish"])` already returned
  `True` for that exact recipe prior to any change in this task. The review's
  specific claim does not hold; bare `"bass"` was never added (by design —
  see the existing inline comment on why the two-word phrase is pinned
  instead) and still isn't. A broader sweep (this task, same rigor as item
  2's own additions) found a REAL, analogous, measured gap instead: `_FISH`
  added `catfish`, `swordfish`, `grouper`, `mackerel`, `perch`, `tilapia` —
  `grouper` is a genuine 1-recipe under-block fix (`imp_096552b6325d5645`
  "Sopa Leao Velloso": grouper alongside shrimp/mussels/clams/crabmeat/
  lobster — was correctly blocked for shellfish/crustacean/seafood allergies
  but NOT for a fish-only allergy before this fix); `catfish`/`swordfish` (4
  corpus hits each) and `tilapia` (1 hit) measured 0 delta (already
  indirectly caught via the pre-existing bare `"fish"` term — both species
  names literally contain the substring "fish", and the tilapia row's own
  ingredient text separately says "fish fillet"); `mackerel` (2 hits)
  measured 0 delta (both rows already carry another `_FISH` term); `perch` (0
  corpus hits) is future-import defense only, matching item 2's own 0-hit
  precedent. No collision risk found for any of the six terms (verified
  against the full active corpus, quarantine sidecar, and seed set).

- **New, standalone: `recipe.allergens` self-reference in
  `_recipe_safety_terms` creates a "shellfish implies fish" false-positive
  artifact** (`app/services/constraint_engine.py`, `_recipe_safety_terms` /
  `contains_allergen`). Discovered 2026-07-20 during the
  `derive_allergen_labels` substring-consistency task's corpus-wide
  invariant testing (see the DONE entry directly above for the full
  measurement: 34/166 apparent "invariant violations", all this one root
  cause). Mechanism: `_recipe_safety_terms` unions ingredient names WITH
  `recipe.allergens` text, and the literal label string `"shellfish"`
  contains the substring `"fish"` — so `contains_allergen(recipe,
  ["fish"])` can return `True` purely because the recipe's OWN, ALREADY-SET
  `allergens` field says `"shellfish"`, independent of any real fish
  ingredient. Direction is fail-safe (over-block, not under-block) so it is
  NOT a release blocker, but it is an unintentional-looking side effect of
  composing raw label strings into the same term pool as ingredient names,
  not a designed rule ("shellfish" and "fish" are legitimately different
  allergen categories — a shrimp-only recipe should not display as
  containing fish). Out of scope for the task that found it (hard
  constraint: zero changes to `contains_allergen`). Options for a future
  pass: (a) leave as documented, accepted fail-safe behavior; (b) exclude
  `recipe.allergens` from `_recipe_safety_terms`'s candidate pool entirely
  and rely solely on ingredient-name substring matching (would need a full
  safety-benchmark re-run to confirm no under-block regression, since some
  existing passing cases might depend on this same union for an unrelated,
  legitimate reason); (c) scope the union more narrowly. No pre-registered
  criteria yet — needs its own FULL TREATMENT consult given it touches
  `contains_allergen`.

- **`derive_allergen_labels` natural-language robustness — ORIGINAL FINDING
  (superseded by the DONE entry directly above; kept for history).**
  (`app/services/constraint_engine.py:553`). Found during task A1's
  scraped-archive re-import (run `20260719T061239Z`, corpus generation
  before the run that actually landed). `derive_allergen_labels` does
  EXACT-SET membership matching (via `normalize_ingredient`, tuned for
  the old Kaggle CSV's already-atomized single-word ingredient names) —
  it fails to reduce natural-language ingredient text with trailing
  descriptor clauses or "X or Y" alternatives (e.g. `"2 eggs, slightly
  beaten"`, `"1/2 cup butter or 1/2 cup margarine, softened"`) to a
  canonical allergen term, unlike `contains_allergen`
  (`_recipe_contains_any_term`), which substring-matches ingredient names
  directly and is what the live app actually gates on
  (`app/graph/nodes.py` -> `constraint_engine.validate_recipe`).
  **Measured impact** (allergen diff report,
  `data/processed/allergen_diff_report_20260719T061239Z.jsonl`): 1,351
  genuine label losses (recipes where the normalized form of a lost label
  is ALSO absent from the new label set — i.e. not just a benign
  synonym-collapse artifact) / 402 recipes gained >=1 label / **0
  serve-time gaps** (every one of the 4,314 individually lost (recipe,
  label) pairs was tested directly against `contains_allergen` itself and
  it still correctly detects the allergen on every case — verified,
  gate added: `serve_time_coverage_gaps_<ts>.jsonl`, always empty so
  far). So this is a METADATA-completeness gap, not a live safety gap —
  but it does mean `recipe.allergens` (Chroma index metadata, UI display,
  the title/instructions-integrity checks' OR-arm) under-covers reality.
  **Proposed approach** (not designed in detail, FULL TREATMENT/advisor
  consult required before implementing): make `derive_allergen_labels`
  substring-consistent with `contains_allergen`'s own matching semantics,
  so it can never regress relative to today — i.e. whatever it derives
  from a "clean" old-style ingredient name must still derive from any
  messier superset string containing that name as a substring.
  **Pre-registered acceptance criteria** (fixed now, before any attempt):
  (1) for every recipe, new derived labels must be a SUPERSET of the
  labels it derives today (`new_labels ⊇ old_labels`) — verified by
  reindexing the corpus and running a fresh allergen diff, zero
  regressions allowed; (2) **zero changes to `contains_allergen` itself**
  — the live safety gate is already correct and must not be touched by
  this fix. **Warning, load-bearing:** never use Chroma `allergens`
  metadata (or any `contains_*`-named Chroma filter) as an EXCLUSION
  filter at retrieval time until this derivation is substring-consistent
  — today it can under-report, and an exclusion filter built on an
  under-reporting label set would admit unsafe rows. (No such filter
  exists in the codebase today — confirmed by search during A1 — this is
  a standing constraint on any FUTURE retrieval-filter design, not a
  currently-live gap.)

- **FULL TREATMENT, safety-adjacent: `MEAT_ALIASES`/diet-type exclusion
  vocabulary gaps exposed by the A1 re-import** — **DONE 2026-07-19,
  advisor-designed fix (A1 revise round 3).** `MEAT_ALIASES` gained
  `bologna`/`bratwurst`/`sirloin`; `_WHEAT` gained `pretzel`/`pita`/`orzo`;
  `_DAIRY` gained `yoghurt`/`curd`; `_SOY` gained `bean curd`;
  `_LOOKALIKE_EXCLUSIONS` gained `"pita": {"pitaya"}` and
  `"curd": {"bean curd", "bean curds"}` (all in
  `app/services/constraint_engine.py`, each with an inline citation
  comment). Audit-side factual correction:
  `scripts/audit_diet_leaks.py`'s `GROUND_TRUTH_FALSE_POSITIVE_PAIRS`
  carves out the bean-curd false positive so the audit agrees with
  production's lookalike exclusion (tests:
  `tests/test_diet_leak_audit.py`'s three audit-side tests). Also required
  a sync fix in `app/services/corpus_import/instructions_ingredient_
  integrity.py`'s independent `MEAT_FLESH_TERMS` set (caught by its own
  pre-existing structural-invariant test,
  `test_meat_terms_are_superset_of_meat_alias_flesh_words`) — releasing 2
  previously-quarantined recipes (`imp_52b1a3c4f7d55036` "Sirloin Steak
  with Mustard and Cream Dressing", `imp_e93630834e7b547c` "Whiskey Sour
  Sirloin") whose own `sirloin` ingredient row is now correctly recognized
  as satisfying their instructions' meat mention. `tests/
  test_diet_leak_audit.py` is green (0/0/0/0 leaks across all four diet
  types) with NO threshold or fixture changes, per vocabulary completeness
  alone. Measured per-term over-block delta (previously-passing recipes
  each NEW term alone now excludes, out of the pre-change passing-baseline
  count — the "gelatin 61/4052" discipline standard): vegetarian —
  `bratwurst` 1/2217, `bologna` 1/2217, `sirloin` 3/2217; vegan —
  `bratwurst` 1/444, `bologna` 0/444, `sirloin` 1/444; gluten-free —
  `pretzel` 4/2031, `pita` 1/2031, `orzo` 1/2031; dairy allergy —
  `yoghurt` 1/1490, `curd` 0/1490; soy allergy — `bean curd` 0/3992 (the
  one recipe that gained a `soy` label in the allergen-diff metadata,
  "Pork in Hot Peanut Sauce", already matched `soy` under the OLD
  vocabulary via a different ingredient — this addition only fixed
  metadata completeness for it, not live coverage). Two sub-items spun out
  as their OWN backlog entries directly below (pepperoni-suppression
  rejected fix, systematic ground-truth-vs-production vocabulary diff).
  Original finding, preserved for context (`app/services/
  constraint_engine.py` — the vegetarian/vegan meat-term table and the
  gluten-free exclusion terms). Found via
  `tests/test_diet_leak_audit.py` going from 0 leaks (all 4 diet types,
  old corpus) to 1/388 (vegan), 3/2046 (vegetarian), 6/1822
  (gluten-free), 3/1323 (dairy-free) leaks on the new corpus written by
  run `20260719T070200Z`. **Root cause, confirmed case-by-case, NOT an
  adapter defect:** every leaking recipe's flagged ingredient term is
  either (a) a self-titled ingredient that was MISSING from the old
  truncated CSV row and is now present for the first time in the richer
  scraped text (the same b9e663c "Curried Peanut Shrimp" corpus-integrity
  pattern, e.g. "Gegrillte Bratwurst" — `imp_fe23c711b0af5a59` — had NO
  `bratwurst` ingredient row at all in the CSV import; "Hobo Buns" —
  `imp_ad294739f1dc5281` — had no `bologna` row), or (b) a previously
  QUARANTINED recipe now RELEASED (9 of the 13 leak instances) whose
  pre-existing meat/gluten term was always there but never reached this
  audit (`test_diet_leak_audit.py` only scans the ACTIVE corpus file,
  never the quarantine sidecar). One case
  (`imp_dca6caf744fc5cc8`, "Country Fried Chicken Steak with Cream
  Gravy") is subtler: its `sirloin tip roast` ingredient never mattered
  for vegetarian either before or after (production `MEAT_ALIASES` does
  not contain "sirloin"/"roast" at all) — in the OLD corpus this recipe
  was accidentally excluded from the "passed filter" bucket by an
  UNRELATED false-positive collision (`pepper` bidirectional-substring-
  matches `pepperoni`), which the new archive's richer descriptor text
  (`"pepper, Freshly Ground"`) broke, removing the accidental exclusion
  and exposing that `MEAT_ALIASES` never actually caught the real meat
  term in the first place. **Specific missing terms confirmed by this
  investigation:** `bratwurst`, `bologna`, `sirloin` (as a bare
  vegetarian-exclusion term; `MEAT_ALIASES` needs this the same way
  `GROUND_TRUTH_MEAT_POULTRY_FISH` in `scripts/audit_diet_leaks.py`
  already has it), plus whatever the gluten-free (pretzel-adjacent) and
  dairy-free leak cases resolve to on a full per-case audit (not yet
  done at the time — resolved above, all four diet types fixed in the
  same pass since every leak traced back to the same handful of missing
  terms). **Was not fixed at the time this was first written** (an
  earlier A1 pass): `constraint_engine.py` was off-limits for that pass
  specifically; the advisor then put it explicitly in scope for the fix
  recorded at the top of this entry.
- **FULL TREATMENT (rejected fix, recorded per advisor instruction,
  2026-07-19): pepperoni-suppression failure mode.** A pepper/pepperoni
  `_LOOKALIKE_EXCLUSIONS` entry was considered and REJECTED to close the
  "Country Fried Chicken Steak with Cream Gravy" masking case (see above)
  — the mechanism doesn't support it. `_is_lookalike_match` strips a
  lookalike PHRASE out of the recipe's own ingredient term, then
  rechecks; a hypothetical `_LOOKALIKE_EXCLUSIONS["pepperoni"] =
  {"pepper"}` entry, applied to a GENUINE "pepperoni" ingredient, strips
  "pepper" out of "pepperoni" leaving "oni" — "pepperoni" is obviously not
  a substring of "oni", so the match is (wrongly) suppressed and a real
  pepperoni ingredient would silently stop counting as meat. Verified by
  direct trace, not just reasoning about the code. **Sibling case, same
  root shape** (bidirectional substring + a short word that is itself a
  prefix of a longer excluded compound term): a bare `"soy"` ingredient
  row reverse-matches `_WHEAT`'s `"soy sauce"` entry (`"soy" in "soy
  sauce"`), so `contains_allergen(recipe, ["gluten"])` and
  `violates_diet_type(recipe, "gluten-free")` both wrongly return `True`
  for a plain soybean ingredient — verified directly, 2026-07-19. Zero
  corpus rows today (`grep`-verified: no bare `"soy"` ingredient name in
  either `imported_recipes.jsonl` or `quarantined_recipes.jsonl`) — pure
  future-import defense, not a currently measured over-block. **This
  sirloin-masking history** (the original discovery vehicle): the
  pepper/pepperoni collision is exactly what accidentally excluded
  `imp_dca6caf744fc5cc8` from the OLD corpus's vegetarian "passed filter"
  bucket for the wrong reason, masking that `MEAT_ALIASES` never actually
  recognized "sirloin" (now fixed separately, see above). **Pre-registered
  acceptance criteria for any future real fix** (design not started):
  bare `"pepper"` must still pass vegetarian; `"pepperoni"` alone must
  still fail; a recipe with BOTH `"pepperoni"` and bare `"pepper"` rows
  must still fail; any measured over-block delta from the fix (recipes
  that flip from failing to passing) must be reported before landing, per
  the "gelatin 61/4052" discipline standard used elsewhere in this file.
  **PRIORITY PROMOTED TO LOAD-BEARING, 2026-07-19 (diet_023 cure round):**
  this is no longer a one-off nuisance. The SAME reverse-arm shape just
  blocked THREE MORE legitimate compound-term additions in the diet_023
  TRUE_VIOLATION cure (`adjudication_20260719T083748Z.md`,
  `app/services/constraint_engine.py` `ALLERGEN_ALIASES["gluten"]`):
  "rice krispies", "grape-nuts", and "corn flakes" could NOT be added as
  their own compound terms (the reverse arm would match every bare
  "rice"/"grape"/"corn" ingredient row corpus-wide) — bare "krispies" and
  "cereal" were added instead, which is a narrower, less precise fix than
  a proper direction-aware mechanism would allow, AND it left a
  known gap: brand-cereal rows that name neither word (e.g. a bare "corn
  flakes" ingredient with no "cereal" suffix) still need one-off manual
  quarantine (see the "corn flakes"/"Post Toasties" manual-quarantine
  entry, this same round, for the 6 ids affected) instead of a systematic
  vocabulary fix. A real direction-aware mechanism (matching a compound
  term as a substring of an ingredient name, but NEVER matching a bare
  ingredient word as a substring of the compound term -- i.e. one-way,
  not `_is_lookalike_match`'s current two-way-then-suppress shape) would
  let "rice krispies"/"grape-nuts"/"corn flakes"/"pepperoni" all be added
  precisely, closing this entire recurring class in one FULL TREATMENT
  pass instead of one narrowly-scoped workaround per incident.
  **DONE 2026-07-20** (commits `4a97b80` + `59a9157`; direction-aware
  implementation removes unsafe reverse-arm bidirectional substring matching,
  unblocks precise compound-term additions, releases 6 manual-quarantine
  recipes via the existing `_ADVISOR_APPROVED_MANUAL_RELEASES` allowlist).
  **Advisor label-amplification note (2026-07-19):** separately,
  `derive_allergen_labels`'s composed `"nuts"` key (`_TREE_NUT | _PEANUT`
  union) means a re-derived `"nuts"` label additionally blocks peanut
  recipes for tree-nut-allergic users and vice versa -- this is
  pre-existing, fail-closed (peanut and tree-nut allergies are
  clinically distinct but frequently co-occur, and the union errs toward
  over-blocking rather than a missed allergen), and NOT a defect; noted
  here only so a future reader of the over-block deltas in this file
  doesn't mistake the `"nuts"` amplification for a new bug.
- **Manual quarantine: brand-cereal rows the "krispies"/"cereal"
  vocabulary addition can't reach** (2026-07-19, diet_023 cure round,
  advisor-directed enumeration). Searched the corpus for brand-cereal
  ingredient names containing NEITHER "cereal" NOR "krispies" (the two
  words just added to `ALLERGEN_ALIASES["gluten"]`) -- found 16 rows
  across 16 recipes: 15 bare `"corn flakes"` rows + 1 `"Post Toasties"`
  row (both real Kellogg's/Post brand cereals with barley-malt flavoring,
  same hazard class as Rice Krispies). Of those 16, 10 already
  independently fail the gluten filter (they also contain a genuine
  wheat ingredient elsewhere in the same recipe, e.g. flour) -- no action
  needed. **6 would otherwise pass the gluten filter** and were
  MANUAL-QUARANTINED this round (`scripts/quarantine_flagged_recipes.py
  --recipe-ids ... --reason "brand cereal with barley-malt risk, pending
  direction-aware lookalike mechanism"`, `check: manual_adjudication` --
  automatically protected against a silent future release by the
  existing `_ADVISOR_APPROVED_MANUAL_RELEASES` allowlist/halt mechanism
  in `scripts/import_corpus.py`): `imp_334d0269ca805812` "Low-Fat Sour
  Cream Potato Casserole", `imp_a4f05171ac765162` "Mallow Sweet Potato
  Balls", `imp_e572df5dc6c557f3` "Flake-and-Fruit Squares",
  `imp_ec6ac830c040514a` "Hash Browns Casserole", `imp_f5b6e366f427503c`
  "Baked Breakfast Potatoes", `imp_f90fc172136c51f8` "Carrot Casserole".
  Superseded by the direction-aware lookalike mechanism (commits `4a97b80` +
  `59a9157`, 2026-07-20): the 6 recipes were auto-released via the
  `_ADVISOR_APPROVED_MANUAL_RELEASES` allowlist mechanism, "corn flakes" and
  "post toasties" added as precise compound terms alongside existing
  "krispies"/"cereal" equivalents.
- **FULL TREATMENT: systematic ground-truth-vs-production vocabulary
  diff — CLOSED 2026-07-20, commit `d200acb`** ("A1 backlog / vocabulary gap
  closure: close the systematic ground-truth-vs-production vocabulary
  diff."). All 17 meat/poultry/fish gaps and 9 dairy gaps listed below were
  added to `MEAT_ALIASES`/`_DAIRY`/`_FISH`/`_MOLLUSK`
  (`app/services/constraint_engine.py`), with the `capon`/`caponata` and
  `tripe`/`striped` collision landmines carved out via
  `_LOOKALIKE_EXCLUSIONS` (plus a third, `brie`/`o'brien`, discovered during
  that change's own over-block measurement) — see commit `d200acb` for the
  full diff and `tests/test_constraint_engine.py`/`tests/
  test_diet_leak_audit.py` for the regression coverage. Measured over-block
  delta versus the pre-change passing baseline: 0 for every term in the
  corpus at that time.
  **Follow-up correction (2026-07-20, `derive_allergen_labels`
  substring-consistency task, same day):** an advisor review of `d200acb`
  claimed `_FISH` was still missing `bass`/`sea bass`, citing a specific
  corpus recipe (`imp_aa6c99eae4fd5f58`, "filets of fresh sea bass") as a
  live under-block. That specific claim was FACTUALLY INCORRECT — `"sea
  bass"` was already a member of `_FISH` since an earlier commit,
  `4bf2377` (2026-07-17), predating `d200acb` itself; `contains_allergen`
  already correctly blocked that exact recipe for fish allergy before
  `d200acb` ever ran. This was a blind spot shared by both production and
  the audit's own ground truth (`GROUND_TRUTH_MEAT_POULTRY_FISH` also never
  listed bare `"bass"`/`"sea bass"` as a gap, since the diff run below never
  flagged it — it wasn't actually missing). The broader review-prompted
  sweep DID find a real, different gap in the SAME `_FISH` set: `grouper`,
  `mackerel`, `perch`, `tilapia` (species already present in this diff's own
  `GROUND_TRUTH_MEAT_POULTRY_FISH` / `MEAT_ALIASES`, per the numbers below,
  but never carried over to `_FISH` itself) plus `catfish`/`swordfish` — all
  six added in the `derive_allergen_labels` substring-consistency task's
  commit; see that task's report / the entry above in this file for the
  measured deltas (one genuine 1-recipe under-block fix, `grouper`; the rest
  measured 0 delta, already redundantly covered).
  Original diff findings, preserved for history (2026-07-19, spun out of the MEAT_ALIASES gap fix above).
  `scripts/audit_diet_leaks.py`'s independent `GROUND_TRUTH_MEAT_POULTRY_
  FISH`/`GROUND_TRUTH_DAIRY`/`GROUND_TRUTH_GLUTEN` sets are the
  hand-authored ground truth the diet-leak audit checks production
  against — every gap found so far (bratwurst, bologna, sirloin,
  pretzel/pita/orzo, yoghurt/curd) was found reactively, one leaking
  recipe at a time. This entry runs that diff systematically, once
  (2026-07-19), against the FULL composed production vocabulary (not just
  the bare base set — e.g. checked against `_VEGETARIAN_EXCLUDED_TERMS`
  for meat, so fish/shellfish terms already covered via that union don't
  false-flag as gaps; checked against `ALLERGEN_ALIASES["gluten"]`, not
  bare `_WHEAT`, so `barley`/`malt`/`rye` don't false-flag either) and
  additionally filters out anything already substring-covered by an
  existing term (so `"chicken broth"` doesn't false-flag when bare
  `"chicken"` already catches it). **gluten: zero real gaps** — every
  `GROUND_TRUTH_GLUTEN` term is already covered by production, once
  substring/composition is accounted for. **meat (vegetarian/vegan),
  17 real gaps, with corpus-hit counts** (2026-07-19, current 4,232-recipe
  corpus): `brisket` 9, `salami` 5, `squid` 3, `anchovies` 1, `capon` 1,
  `grouper` 2, `mackerel` 2, `meatball` 1, `tilapia` 1, and 8 terms with 0
  corpus hits today (`calamari`, `caviar`, `octopus`, `perch`, `pheasant`,
  `quail`, `tripe`, `venison`) — future-import defense only. **dairy
  (allergy + dairy-free), 9 real gaps**: `gruyere` 8 (already a known,
  separately-tracked item — see "Gorgonzola / gruyere PDO-verification
  cluster" at the top of this file, a DIFFERENT question (vegetarian
  rennet status) than this one (dairy-allergen status) — gruyere is
  unambiguously dairy regardless of rennet source, so this gap is real
  independent of that cluster's outcome), `provolone` 7, `creme fraiche`
  5, `custard` 5, `brie` 3, `kefir` 2, `camembert` 1, `queso` 1, `gouda` 0.
  **Not fixed here** — this is the diff + measurement only, per the
  advisor's instruction to file it as its own FULL TREATMENT item, not to
  land it inline with the reactive fixes above. The `brisket`/`salami`/
  `gruyere`/`provolone` entries in particular have real, nonzero corpus
  presence and should be prioritized over the 0-hit terms when this is
  next picked up.
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
- **Remaining cooked-variant density leak class** (advisor A2-revision #2,
  `app/utils/unit_converter.py`). The strict-first fix above only closes
  the specific spelling given an explicit table key (`"cooked rice"`,
  `"cooked white rice"`); any other "X, cooked" comma phrasing still falls
  through to the legacy `normalize_ingredient` tier, which strips
  `"cooked"` as a `DESCRIPTORS` entry and returns the *uncooked* density.
  Exact probe strings that currently leak (verified 2026-07-19):
  `_density("rice, cooked")` returns `0.85` (uncooked), not `0.67`
  (cooked) — same root cause, comma form. Other "X, cooked" phrasings for
  any ingredient with both a cooked and uncooked table entry are likely
  affected the same way (none currently exist besides rice, so the blast
  radius today is exactly this one probe). Fix shape, not yet decided:
  either add explicit comma-form keys (`"rice, cooked"`) alongside the
  space-form ones, or teach `_normalize_for_density_lookup` to also try a
  comma-swapped variant (`"X, cooked"` -> `"cooked X"`) as an additional
  strict-tier candidate before the legacy fallback — the latter is more
  general but needs its own advisor sign-off since it changes the
  precedence-tier contract, not just the tables.
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
  quarantine** — **DONE (re-run, not re-pinned) 2026-07-19, task A1.**
  `python scripts/evaluate_retrieval.py` re-run twice: once against the
  A1 corpus before the diet_023 cure (3,859 active + 25 seeds = 3,884
  indexed, `data/evaluation/retrieval_eval_baseline_20260719T104216Z.md`)
  and once more against the FINAL cured corpus (3,853 active + 25 seeds =
  3,878 indexed, after the diet_023 cure's 6-recipe manual quarantine,
  `data/evaluation/retrieval_eval_baseline_20260719T120000Z.md` —
  superseding both the original `docs/phase-1.5-closeout.md` §4 baseline
  and the intermediate `104216Z` file), both marked non-comparable to
  prior baselines per this item's own original ask. **GATE RESULT: PASS**
  on both runs (both gated categories — dish, dietary — win on
  semantic-vs-keyword MRR+Recall@10 and stay within hybrid tolerance).
  Not formally "re-pinned" into `docs/phase-1.5-closeout.md` itself (that
  document's own pin is a separate, deliberate editorial action out of
  this task's scope) — the dated artifact file (`120000Z`, the final one)
  is the re-baseline of
  record until/unless a human re-pins it there. Not ship-blocking, as
  originally noted.
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

- **Scraper/scraped-HTML untrack: history-rewritten 2026-07-19.** The
  untrack was initially forward-only (2026-07-19 morning), but before any
  push the human instructed that these files also be removed from history.
  All 7 unpushed local commits were rewritten via `git filter-branch
  --index-filter` to remove `app/services/recipe_scraping/` (package),
  `scripts/scrape_recipe_pages.py`, `tests/test_recipe_scraping.py`, and
  `tests/fixtures/scrape/*.html` entirely. Since origin/main had never
  received these commits, the scraper code and captured HTML pages have
  therefore **never been published to the remote**. Files remain on disk,
  gitignored, per the human's 2026-07-19 hobby-scope licensing decision
  (see `docs/DEPLOY.md` "Scraped-archive licensing").

  **Commit hash mapping** (old → new, all unpushed):
  - 39a80c1 → 001453f (A1 follow-up: untrack scraper package + deploy prep)
  - 5b62b55 → d93e07a (A1: rebuild corpus from scraped Food.com archive)
  - ec58eed → 6482c6b (A2: widen deterministic unit-conversion surface)
  - 14fca83 → 8bb4871 (C0: fix stale benchmark disclaimer)
  - bb6980f → d67fec6 (Roadmap: status snapshot + forward plan)
  - 1a42738 → 89c3cdd (Backlog: record deferred items)
  - 6090a75 → 258af1a (Corpus enrichment: scraper)

  **Note:** Timestamped evaluation artifacts under `data/evaluation/`
  (e.g. `safety_benchmark_report_20260719T*.md`,
  `adjudication_20260719T115815Z.md`) still cite old hash `ec58eed`, which
  corresponds to rewritten commit `6482c6b` — those records are deliberately
  left unmodified. The only tree difference between old `ec58eed` and new
  `6482c6b` is the removal of the local-only scraper files, which do not
  affect benchmark behavior.
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

## Deterministic substitution engine (Phase 3)

See `app/services/substitution_service.py`'s module docstring for the full
account of what was found and deferred; summarized here with enough detail
to act on:

- **Corpus-wide substitution coverage.** `SUBSTITUTION_EDGES` is a
  hand-curated ~10-edge starter set (dairy, peanut, gluten/wheat, egg,
  vegetarian/vegan gelatin+honey+broth). Deferred: a systematic pass over
  the active corpus's most common rejected-ingredient classes (mirroring
  `scripts/audit_diet_leaks.py`'s methodology) to find the highest-value
  next edges to add, plus expanding beyond the current allergen/diet
  coverage (e.g. sesame, tree nut).
- **"X or Y" alternative ingredient rows.** `_matching_edges` matches a row
  as-is; a row like "butter or margarine" is not parsed into alternatives
  and only matches if the literal substring happens to be present. Explicitly
  out of scope for v1 per the task spec.
- **Context-sensitivity (e.g. butter in pastry vs. sauté).** The
  `butter -> olive oil` edge's citation already discloses this limitation
  (works for sautéing/cooking, not for laminated pastry/creaming-method
  baking) rather than silently overclaiming. A context-aware version would
  need to read the recipe's own instructions/technique, not just its
  ingredient list -- deferred.
- **Multi-ingredient/ratio-aware swaps.** v1 is equal-measure, single-
  ingredient-at-a-time only (per the task spec). Two edges' citations
  disclose a real ratio mismatch: `egg -> ground flaxseed` (real ratio is 1
  tbsp flaxseed + 3 tbsp water per egg, not equal-measure) and
  `gelatin -> agar agar` (agar gels more strongly per unit volume than
  gelatin). Neither is a safety concern (over/under-gelled or
  under-bound is a texture problem, not an allergen one), but a future
  ratio-aware pass should special-case these two first.
- **`_LOOKALIKE_EXCLUSIONS`-style carve-out for compound "X milk"/"X cream"/
  "X pasta" terms in `app/services/constraint_engine.py`.** Discovered
  while curating this task's edges (see `substitution_service.py`'s module
  docstring for the full list): `ALLERGEN_ALIASES["dairy"]`'s bare "milk"/
  "cream"/"butter" terms and `ALLERGEN_ALIASES["wheat"]`'s bare "pasta"
  term substring-match INSIDE plant-based/gluten-free compound names that
  are not actually dairy/wheat ("oat milk", "coconut cream", "coconut
  milk", "gluten-free pasta", "rice pasta" all self-flag). This is the
  SAME false-positive shape `_LOOKALIKE_EXCLUSIONS` already fixes for
  "water chestnut"/"romano bean"/"bean curd"/"caponata"/"striped bass"/
  "o'brien" -- a genuinely different food that happens to contain the
  allergen term as a literal substring, not real ambiguity that should
  resolve toward blocking. NOT fixed here: `constraint_engine.py` is
  explicitly off-limits for this task, and this is a FULL TREATMENT,
  safety-adjacent change (touches allergen matching) that needs its own
  advisor consult -- candidate carve-outs, once picked up: `{"milk":
  frozenset({"oat milk", "soy milk", "almond milk", "coconut milk", "rice
  milk", "cashew milk", "hemp milk", "pea milk"})}`, `{"cream": frozenset
  ({"coconut cream"})}`, `{"pasta": frozenset({"gluten-free pasta", "rice
  pasta", "chickpea pasta", "lentil pasta", "corn pasta", "quinoa
  pasta"})}` -- each needs the same per-(term, recipe_term) pairwise
  verification the existing table's entries document (a real dairy/wheat
  ingredient alongside a lookalike in the SAME recipe must not have its own
  match suppressed; see that table's module comment).
- **`tree nut`/`nuts`/`nut` ALLERGEN_ALIASES keys' literal-substring
  collision with "coconut".** Also discovered during this task's curation
  (`derive_allergen_labels(["coconut"])` returns `["nut", "nuts"]`, and any
  bare "nut"/"nuts" user allergy string reaches this same match): the bare
  ALLERGEN_ALIASES key "nut" (added this session for the bare-singular-noun
  fix) is expanded as an ordinary substring term by `derive_allergen_labels`/
  `contains_allergen` when the ALLERGEN_ALIASES KEY itself is "nut"/"nuts"
  (as opposed to reaching the tree-nut/peanut vocabulary through an alias
  expansion), and "nut" is a literal substring of "coconut" (co-co-NUT).
  Over-cautious (coconut is not FALCPA/EU-listed as one of the enumerated
  tree nuts), not unsafe -- but wide-reaching (every "coconut ..."
  ingredient in the corpus). Not fixed here (constraint_engine.py
  off-limits); flagging because it affected which substitute names could be
  curated in this task (no coconut-based dairy substitute could be added
  without also picking up this flag) and is likely to surprise a future
  editor. Needs its own advisor consult (is this drift from the "nut"
  singular-key fix intentional/acceptable, or a regression to fix?) before
  any change.
- **`soy sauce -> tamari`/`egg -> flax egg` are impossible under the current
  vocabulary, by design of pre-existing (unrelated) fail-closed policies.**
  `SYNONYMS` maps both "tamari" and "gluten free tamari" to "soy sauce"
  (`app/utils/ingredient_normalizer.py`, a deliberate, documented
  fail-closed choice -- see `_WHEAT`'s comment in `constraint_engine.py`),
  so tamari can never clear this system's gluten check under any name; "flax
  egg" contains the literal substring "egg" and self-triggers the very
  allergen it exists to avoid. This task substituted `coconut aminos` and
  `ground flaxseed` respectively instead (see `substitution_service.py`'s
  module docstring for the full verification) -- not a gap, just recorded
  here so a future editor doesn't "fix" the naming back to the more
  obvious-looking one without re-discovering why it can't work.
- **`sour cream <-> Greek yogurt` and `heavy cream -> coconut cream/milk`
  edges were dropped, not built.** Both original_terms and the naive
  substitute name are members of `ALLERGEN_ALIASES["dairy"]` under the
  current vocabulary (Greek yogurt is an explicit `_DAIRY` member; "cream"/
  "milk" are bare `_DAIRY` terms substring-matching every coconut-cream/
  coconut-milk naming), so no honest `resolves` claim could be curated for
  either pairing without failing the mandatory curation-invariant test (by
  design -- the test caught this, it is not a test bug). If the
  `_LOOKALIKE_EXCLUSIONS`-style carve-out above ever lands, revisit
  `heavy cream -> coconut cream`/`coconut milk` then; `sour cream <->
  Greek yogurt` has no path forward under this vocabulary at all (both are
  genuinely, unambiguously dairy) and would need a different constraint
  key entirely (e.g. a "lactose" allergy this project doesn't model) to
  ever mean something for allergy/diet resolution.
- **`_EDGE_MATCH_EXCLUSIONS` in `substitution_service.py` is a small,
  hand-curated list (currently just "butter" vs. "peanut/almond/cashew/
  cocoa/apple/sunflower(-seed) butter"), not a general fix.** Softer
  cross-matching cases were found and deliberately left unaddressed: the
  `milk -> oat drink`/`soy drink` edges also match "buttermilk" (a distinct
  product; swapping it for a plain plant milk is not absurd the way
  "peanut butter -> olive oil" is, so this was judged lower-priority, not
  ignored by oversight). Extend `_EDGE_MATCH_EXCLUSIONS` if a future case
  surfaces a real problem from this.
- **Variant recipe titles never updated by `_build_variant_recipe`.**
  `app/services/substitution_service.py`'s `_build_variant_recipe` function
  (the core builder for serving-time ingredient swaps) deliberately leaves
  `Recipe.title` unchanged — it swaps only `ingredients`/`allergens`/`nutrition`/
  `source_type`/`substitution_note`, never the title. This caused all 4 new
  safety-benchmark judge flags in the Phase 3 task (subst_001/005/006/009,
  `data/evaluation/adjudication_20260720T184648Z.md`): the judge's title-
  substring check saw the old allergen name still present in the title (e.g.
  "Hershey's Chewy Peanut Bars") even though the actual served ingredient list
  had been independently confirmed clean (peanut butter swapped to sunflower-
  seed butter). All 4 flags were adjudicated **JUDGE_FP** (confirmed by two
  independent advisor reviews) — this is a real, if non-safety, UX/labeling
  gap, not a safety defect. Deferred fix: deterministic, templated title
  annotation (e.g. append "(peanut-safe variant)" to `Recipe.title` when a
  substitution is applied), explicitly NOT built reactively just to silence
  a judge flag — it's a real UX improvement deferred to a future pass.

## Day planner (B3, macro-targeted day planning)

- **Enumeration-scaling trigger, pre-registered.** `app/services/day_planner.py`
  (`_enumerate_multisets`, called from `assemble_plan`) does exhaustive
  `combinations_with_replacement` enumeration over the trusted candidate
  pool — correct and fast at today's pool size (~15: C(18,4)=3,060 for
  K=4), but it is O(pool^K) and does not scale. **Trigger: when the
  trusted pool (`app.services.nutrition_view.trusted_per_serving` count,
  see the "CRUX FINDING" in `day_planner.py`'s module docstring) exceeds
  ~200 recipes, exhaustive K=4 enumeration (C(203,4)≈68M) becomes too slow
  — replace the enumerator then, not before.** The module is deliberately
  structured (enumerate-then-score, `_enumerate_multisets` isolated) so the
  swap to a smarter search (branch-and-bound or DP over a discretized
  macro-space) only has to replace that one function; `assemble_plan`/
  `assemble_day_plan`/`assemble_remaining_meal`'s public signatures and the
  `DayPlan` schema (`app/schemas/day_plan.py`) should not need to change.
- **Continuous/fractional serving scaling (deliberately deferred from v1).**
  `app/services/day_planner.py` selects only whole recipe servings by
  design — see the module docstring's "WHOLE-SERVINGS ONLY (v1)" section.
  Continuous scaling could reuse `app.schemas.ingredient.scale_ingredients`
  (roadmap item B2) to let a recipe contribute a fractional serving toward
  a target. Explicitly NOT done in B3 because it would make the
  +/-10%/+/-15% tolerance gate trivially satisfiable for almost any target
  (any target becomes "reachable" by scaling a single recipe to fit
  exactly), gutting the point of `scripts/evaluate_day_planner.py`'s
  feasibility numbers. If this is picked up later: keep whole-servings
  mode available too (report both), and re-register a new tolerance/eval
  design with the advisor before shipping continuous scaling — this is a
  FULL TREATMENT change, not mechanical.
- **Honest technical note for the orchestrator/human (not a code change):**
  the day planner's real-world usefulness is capped by the trusted pool
  size, not by the algorithm. As of the A3 corpus (3,878 recipes,
  2026-07-20), `trusted_per_serving` returns a real number for exactly 15
  recipes — everything else is PARTIAL (undercounts, silently excluded) or
  UNGROUNDED. `scripts/evaluate_day_planner.py`'s "realistic-round" bucket
  measured 3/4 (75%) feasibility against that 15-recipe pool on this run;
  that number moves only if/when overall grounding coverage (A2/A3-class
  work) improves the trusted-pool size, not by touching
  `app/services/day_planner.py`. No marketing claim about this feature
  should describe it as covering "the corpus" (3,878 recipes) — it
  currently operates over the ~15-recipe trusted subset only.

## Meal-prep batch solver (Phase 4 item 1, app.services.batch_planner)

- **Ingredient-sharing scoring — deliberately dropped from v1 (design
  consult, decided).** `app.services.batch_planner.assemble_batch_plan`
  selects the 2-3 batch recipes by per-container macro fit alone
  (`(kcal_relative_error, protein_relative_error)`); it never scores,
  ranks, or optimizes for ingredient overlap among the selected recipes.
  Whatever overlap exists shows up naturally in the consolidated shopping
  list (`app.services.procurement_service.build_shopping_list_for_items`)
  but is incidental, not a designed objective — do not describe
  ingredient-sharing as "optimized" anywhere (code comments, docstrings,
  API docs, UI copy). **Revisit trigger (pre-registered):** once the
  trusted pool (`app.services.nutrition_view.trusted_per_serving` count,
  same metric `docs/BACKLOG.md`'s day-planner "Enumeration-scaling
  trigger" entry uses) reaches roughly the same ~200-recipe mark AND
  eligible sets (recipes passing `_container_eligible` for a given target)
  routinely exceed `max_recipes` (today, at a ~15-recipe pool, the
  eligible set rarely exceeds 3 — see `scripts/evaluate_batch_planner.py`'s
  bucket 2 `eligible_recipe_count` column), making ingredient overlap a
  REAL tiebreak choice among otherwise-comparable candidates rather than a
  moot one. Design not started; would need its own FULL TREATMENT consult
  (this module's own tier) since it changes the selection algorithm, not
  just a scoring weight.
- **Honest technical note for the orchestrator/human (not a code change),
  mirrors the day-planner's own entry above:** the batch solver's
  real-world usefulness is capped by the same ~15-recipe trusted pool the
  day planner shares (`app.services.nutrition_view.trusted_per_serving`,
  A3 corpus, 2026-07-20) — this solver's PER-CONTAINER band (every
  selected recipe's own per-serving macros must individually fit the
  target, not just their sum) is additionally a HARDER constraint than the
  day planner's summed +/-10%/+/-15% band, so the realistic-round bucket's
  feasibility number is expected to be lower/more volatile than
  `scripts/evaluate_day_planner.py`'s own — see
  `scripts/evaluate_batch_planner.py`'s own module docstring and its
  pre-registered target list (500/40, 600/45, 450/35, 700/50) for the
  measured numbers on any given run. That number moves only if/when
  overall grounding coverage improves the trusted-pool size, not by
  touching `app/services/batch_planner.py`. No marketing claim about this
  feature should describe it as covering "the corpus" — it currently
  operates over the ~15-recipe trusted subset only, same as the day
  planner.

## Weekly meal-plan solver (Phase 4 item 2, app.services.weekly_planner)

- **"All days come out identical" — a known, honest, human-visible product
  truth, stated loudly, not a bug.** `app.services.weekly_planner.
  assemble_week` is a THIN COMPOSITION of B3
  (`app.services.day_planner.assemble_day_plan`, called `days` times, same
  candidates/target every time) — recipe selection is macro-only and
  pantry-independent (macros don't depend on pantry state, so there is no
  day-to-day pantry-depletion state to carry between calls), and the
  trusted pool is tiny (~15 recipes as of the A3 corpus, 2026-07-20 — see
  `app.services.day_planner`'s "CRUX FINDING"). Given that, EVERY call to
  `assemble_day_plan` inside a single `assemble_week` run is fully
  deterministic and receives identical inputs, so **every day in a
  `WeeklyPlan.days` typically comes back structurally identical** (the same
  day-plan repeated `days` times) — confirmed by
  `scripts/evaluate_weekly_planner.py`'s `all_days_identical` reporting
  column on every bucket-2 target it ran (2026-07-20/21: `True` for all 3
  realistic-round targets at the then-15-recipe pool). This is documented
  on `app.schemas.weekly_plan.WeeklyPlan`'s own docstring and
  `app.services.weekly_planner`'s module docstring, both loudly, per this
  task's own instruction not to bury it. It stops being true once
  day-to-day variety (below) or the trusted pool grows enough that
  different days could legitimately draw different combos for the same
  target — neither is built yet.
- **Day-to-day variety — deliberately dropped from v1 (thin-composition
  design, decided).** No mechanism exists to make different days of a week
  select different recipe combos for the same target (e.g. round-robin
  across near-tied combos, or a diversity-aware secondary sort key) — every
  day independently calls `assemble_day_plan` with the SAME inputs and gets
  the SAME (correctly) globally-best answer. **Revisit trigger
  (pre-registered, same numeric criterion `docs/BACKLOG.md`'s day-planner
  "Enumeration-scaling trigger" and the batch solver's "Ingredient-sharing
  scoring" entry both use):** once the trusted pool
  (`app.services.nutrition_view.trusted_per_serving` count) reaches roughly
  the ~200-recipe mark, there will typically be multiple combos within
  tolerance for a given target, at which point picking a DIFFERENT
  near-optimal combo per day becomes a real, meaningful choice rather than
  a moot one at today's ~15-recipe pool (where there is often exactly one
  best combo, or none). Design not started — would need its own FULL
  TREATMENT consult (this module's own tier), since it changes
  `assemble_week`'s per-day selection logic, not just a reporting field.
- **Pantry-utilization as a scored objective — deliberately dropped from
  v1 (thin-composition design, decided), same shape as the batch solver's
  "Ingredient-sharing scoring" entry above.**
  `app.services.weekly_planner.compute_pantry_utilization` is REPORTED
  ONLY (`WeeklyPlan.pantry_utilization` /
  `WeeklyPlan.uncompared_ingredient_count`) — it never influences which
  recipes `assemble_day_plan` selects, and recipe selection stays
  macro-only. Do not describe pantry utilization as "maximized" or
  "optimized" anywhere (code comments, docstrings, API docs, UI copy).
  **Revisit trigger (pre-registered, same numeric criterion as the two
  entries directly above):** once the trusted pool
  (`app.services.nutrition_view.trusted_per_serving` count) reaches roughly
  the ~200-recipe mark AND there are routinely multiple within-tolerance
  combos to choose between for a given target (the same precondition
  "Day-to-day variety" above needs), pantry coverage becomes a real
  tiebreak/objective choice among otherwise-comparable candidates rather
  than a moot one at today's tiny, mostly-single-best-combo pool. Design
  not started — would need its own FULL TREATMENT consult (this module's
  own tier), since it changes the selection algorithm, not just a scoring
  weight; this is also a hard PREREQUISITE for perishable sequencing below
  (sequencing which ingredient to use first only matters once utilization
  is actually being optimized for, not just reported).
- **Perishable sequencing — deferred entirely, not built at all (not even
  a partial version).** The roadmap line ("users log rough purchase dates
  for perishables; system nudges 'use your spinach today'") implies a real
  "use the ingredient that expires soonest, first" ordering across the
  week's shopping/prep sequence — this module does not attempt that.
  Blocked on TWO things, in order: **(a)** a real purchase-date/expiry-date
  model with actual ORDERING information. As of this task
  (2026-07-20/21), a concurrent Phase 4 item ("expiry/waste tracking",
  touching `app/schemas/inventory.py` and the new
  `app/services/waste_tracking.py` — uncommitted/in-progress in the shared
  tree at the time this was written, not relied on here since it was
  off-limits to read-and-depend-on mid-flight) is adding
  `ConfirmedIngredient.purchase_date` / `.days_until_expiry()` on top of
  the pre-existing bare `expires_soon: bool` — check its landed state
  before starting; even once landed, per-ingredient purchase dates alone
  give a per-item countdown, not yet a week-level SEQUENCING plan (which
  ingredient across which day's recipes to prioritize first). **(b)**
  pantry-utilization becoming a real SCORED objective first (the entry
  directly above) — sequencing which ingredient to use first is only a
  meaningful question once the solver is actually choosing recipes partly
  to consume pantry stock, not just reporting coverage after the fact.
  Design not started for either half.

## Safety-tools API / MCP (Phase 5, "expose the constraint engine as an
## API/MCP server" — 2026-07-20)

- **MCP server: deliberately skipped this pass, REST-only shipped.** No
  MCP-related dependency or scaffolding exists anywhere in this repo today
  (`requirements.txt`/`pyproject.toml` grepped, `python -c "import mcp"`
  fails — package not installed). Adding an MCP SDK dependency purely to
  wrap 4 already-existing REST endpoints is exactly the "forced,
  unjustified dependency" CLAUDE.md warns against for a ship-first item
  with no design ambiguity otherwise. `app/api/routes_safety_tools.py`
  ships the REST surface only (`POST /tools/validate-recipe`,
  `/tools/check-allergen`, `/tools/check-diet-violation`,
  `/tools/derive-allergen-labels`). If MCP access is picked up later: build
  it as a thin wrapper that calls these same 4 REST endpoints (not
  `constraint_engine` directly a second time), so there is exactly one
  implementation of "what does this endpoint do" — this was pre-decided in
  the task spec for this item and should still hold when MCP is added.
- **Rate limiting for `/tools/*`: IP-keyed, not session-keyed — a
  deliberate, flagged deviation from the existing pattern.** Every other
  rate-limited endpoint (`/library/discover`, `/recipes/recommend`,
  `/library/reindex`) requires a signed `X-Session-Token`
  (`app.dependencies.get_session_user`) that only the trusted Streamlit
  frontend process can mint (`mint_session_token` is never exposed via any
  HTTP endpoint an external caller could hit). Requiring that same token on
  `/tools/*` would make the surface unreachable by exactly the audience
  this roadmap item exists to serve ("an external AI agent/developer could
  call to get deterministic allergy/diet safety filtering without needing
  MacroChef's full recommend pipeline"). Implemented instead:
  `app.dependencies.require_safety_tools_rate_limit`, which reuses the same
  `RateLimiter` singleton/sliding-window algorithm (`get_rate_limiter()`,
  `app/services/rate_limiter.py` — unchanged) and the same
  `Settings`-driven limit/window config pattern
  (`RATE_LIMIT_SAFETY_TOOLS_MAX` / `RATE_LIMIT_SAFETY_TOOLS_WINDOW_SECONDS`,
  default 60/hour), but keys on caller IP
  (`request.client.host`) instead of a verified session user id. This is a
  weaker identity (spoofable behind a shared NAT/proxy, and reflects
  whatever the ASGI server reports unless a reverse proxy is configured to
  forward the real client IP) — an accepted, documented limitation for a
  ship-first abuse guard, not a security boundary; these endpoints hold no
  secrets, no per-user data, and make no safety decision of their own (see
  `app/dependencies.py`'s inline comment at
  `require_safety_tools_rate_limit` for the full reasoning). **Flagged for
  explicit orchestrator/human review**, not silently assumed — CLAUDE.md
  lists "rate limiting" among the FULL TREATMENT categories generally, and
  this task's own spec pre-classified the whole item as not needing
  advisor consult on the premise that it adds "no new safety DECISION, only
  new ACCESS" to already-approved logic; the auth-mechanism choice here is
  an access/abuse-control decision, not an allergy/diet safety decision,
  but it's still worth a second look given CLAUDE.md's general framing. If
  IP-keying proves too weak in practice (e.g. real abuse from a shared
  IP), the next step is a per-API-key identity for external tool callers,
  not tightening this back to session-token auth (which would defeat the
  endpoint's purpose).
