# Instructions-vs-ingredients integrity check — pre-registered spec

Advisor consult (MODE: ADVISE, Fable 5), 2026-07-17. This is the
implementable spec for the corpus-wide instructions-vs-ingredients
cross-check required by the 165139Z advisor review (finding 6) before
the next gate-claiming benchmark run. FULL TREATMENT end-to-end: the
implementation returns to the advisor (MODE: REVIEW) with the code, the
dry-run report, the guard verdicts, and the sample-audit record BEFORE
any quarantine is applied.

**Pre-registration rule: every numeric band in this document was fixed
blind — the advisor deliberately ran no candidate check over the corpus
before setting them. Vocabulary and bands are frozen before the first
full-corpus run; the first run's counts are reported regardless; any
post-result vocabulary revision is documented in the report's
"revisions" section with before/after counts.**

## 1. Detection scope

Three tiers. One new module, pure regex, no LLM anywhere,
precision-first for the quarantine tiers, with a committed report tier
for the residue adjudication handles.

- **Tier A (auto-quarantine): safety-vocabulary cross-check.**
  Hand-authored allergen category terms + meat flesh words +
  wheat/gluten terms, scanned over `instructions` steps, cross-checked
  against ingredient rows + the `allergens` field. This is what the
  gate protects: a hidden ingredient only matters if the constraint
  engine would have blocked it had it been listed.
- **Tier B (auto-quarantine): undisclosed standalone stock.** Triggers:
  `stock`, `broth`, `bouillon` only. Rationale: (i) adjudication rule 3
  already treats undisclosed stock as default-TRUE for veg/vegan and
  allergy constraints — leaving it to adjudication guarantees
  non-convergence (Dirty Rice, Rice/Apple/Raisin Dressing are live
  examples); (ii) unlike "dough"/"batter", stock is never a composite
  of listed rows — it is a purchasable component whose absence is
  unambiguous; (iii) word-boundary-safe with one suppression
  ("stock pot").
- **Tier C (report-only, never quarantines): curated generic residue.**
  `oil`, `dough`, `batter`, bare `meat`, `sauce`, `gravy`. Too
  polysemous or too often composites-of-listed-rows to quarantine
  deterministically ("pour the batter" from listed flour; "the meat" of
  a crab; "grease with oil"). The committed report gives future
  adjudications per-row evidence.
- **Explicitly out of scope, documented:** non-safety-vocabulary
  omissions (the imp_f9cc221553155bfc "orange juice" class). Hidden
  orange juice cannot produce an engine-visible allergy/diet violation
  — full food-word generality is impossible and unnecessary for the
  gate. The check's report states this boundary.
- **Title side: unchanged.** This check reads `instructions` only.
  Bare-"fish"/meat-word title checking is proven impossible to do
  safely ("Fish Marinade", "Marinade for Beef" class); in practice the
  corrupt rows' instructions name the meat. The title-side residual is
  recorded in `docs/BACKLOG.md`.

**Adjudication conventions pre-registered alongside (surfaced to the
human in the NEEDS HUMAN summary since they shape how the human-owned
gate is adjudicated):** (1) a Tier-C generic-`oil` omission with no
named oil variety is JUDGE_FP-eligible for all constraints (commodity
default oils are not allergens in the engine's vocabulary), but must be
affirmatively written per case citing the Tier-C report; (2)
orange-juice-class omissions likewise. These are per-case adjudication
conventions of the kind the base adjudication already established, not
amendments to the gate semantics.

## 2. Matching rules

**Core asymmetry — the load-bearing design decision:**

- **Triggering (instructions side) is STRICT:** word-boundary regex
  with optional trailing `s` (reuse the `_find_term_spans` pattern),
  longest-phrase-first span consumption (so "peanut butter" consumes
  the span and bare "butter" can't also fire), plus the suppressions
  below.
- **Satisfaction (ingredient-rows side) is LENIENT:** a category
  mention is satisfied if any ingredient row word-boundary-matches any
  term in that category's satisfier list, OR the category's
  `allergen_labels` intersect `recipe.allergens` (mirror the title
  module's OR-arm rationale), OR a per-category lenient extra applies.
  Rationale: this is a *completeness* check, not an allergen classifier
  — a "coconut milk" row plausibly IS the "milk" the instructions
  reference, a "margarine" row plausibly IS the "butter", a "rice
  flour" row IS the "flour". The serving-time engine independently
  handles actual allergen semantics; asymmetric leniency here is what
  keeps quarantine precision high without weakening safety.

**Step-local rules** (`instructions` is `list[str]`; each element is a
step — all contextual rules apply per-step, never whole-text):

- **Negation (step-local, occurrence-local):** a match is suppressed
  only if ITS step contains `omit`, `without`, `instead of`,
  `in place of`, `no <term>`, `<term>-free`, `do not add`,
  `leave out`. Matches in other steps still count. (This differs from
  the title module's term-global negation: imp_997819df41245ec6 has
  "Variation: … Omit almonds" (suppressed) AND "Add lemon zest and
  almonds" (must still flag — and does).)
- **Intended-use/serving cues (step-local):** suppress matches in steps
  containing `serve with`, `serve over`, `serve alongside`, `serve on`,
  `use as`, `use it as`, `use to`, `use on`, `when you cook`,
  `when cooking`, `when grilling`, `when serving`, `goes well with`,
  `great with`, `delicious with`. This clears "Fish Marinade" ("Use as
  a marinade, Then as a basting sauce when you cook fish") while "Cut
  the fish into small pieces and mix through" (Spicy Fish Cakes) has no
  cue and flags.
- **Preceding-token suppressions** (span-local, immediately-preceding
  word — deliberately NOT the title module's whole-text modifier rule,
  which would over-suppress in long instructions): `butter` preceded by
  fruit/nut/seed words (apple, pear, peach, plum, apricot, pumpkin,
  quince, fig, mango, cranberry, cherry, strawberry, peanut, almond,
  cashew, sunflower, cocoa, nut, seed); `milk` preceded by
  coconut/almond/soy/soya/rice/oat/cashew/hemp; `flour` preceded by
  corn/rice/potato/tapioca/almond/coconut/chickpea/soy/oat/quinoa
  (non-wheat flours are not wheat evidence — "almond flour" still fires
  tree-nut via its own "almond" span); `chestnut` preceded by "water"
  (mirror `_LOOKALIKE_EXCLUSIONS`).
- **Exact-phrase suppressions (tool/brand/idiom, each cited):**
  `pastry blender` (live in imp_9ff0ac08d2b353ca's own text),
  `pastry brush`, `pastry bag`, `pastry cutter`, `pastry cloth`,
  `biscuit cutter`, `bread machine`, `bread knife`, `bread board`,
  `stock pot`/`stock-pot`, `cape cod`, `cracker barrel`,
  `grape-nuts`/`grape nuts`, `oyster cracker(s)` (suppresses oyster
  only; "cracker" still evaluable), `fish out`, `egg-plant`, and a
  per-step `mock <anything>` rule (reuse the title module's "mock"
  convention, applied per-step).
- **Commonly-unlisted items:** `water`, `salt`, `pepper`, `ice` are
  never triggers (simply absent from the vocabulary).
- **Morphology:** optional `s?` suffix only, as in the existing module.
  Add explicit literal terms `breaded` and `floured` to wheat triggers
  rather than a general `(ed|ing)?` suffix (which would create
  "fished"/"creamed" homograph problems). Bare `cream` is NOT an
  instruction trigger at all ("Cream together butter and sugar" is a
  verb — live in imp_6ab74a6c238451a3); only multiword forms
  (`heavy cream`, `sour cream`, `whipping cream`, `whipped cream`,
  `light cream`, `double cream`, `half-and-half`, `half and half`).

**Category vocabulary (starter lists; the module hand-authors these
independently of `ALLERGEN_ALIASES`, same independence rationale as the
title module; every later addition/removal during FP-fixing must carry
a cited real corpus example, per that module's established
convention):**

- `nut` (bare, NEW — combined peanut/tree-nut): triggers `nut`, `nuts`
  (word boundary alone disposes of nutmeg/doughnut/butternut/coconut/
  donuts — no boundary exists inside those words). Satisfiers:
  `nut`/`nuts` + all peanut + tree-nut terms; labels {nuts, tree nut,
  peanut, peanuts}. Coconut is NOT a satisfier.
- `peanut`: triggers peanut(s), groundnut(s), `ground nut` /
  `ground nuts` (two-word form live in imp_d34a2ab621245cba: "ground
  nut oil"), satay. Satisfiers same + labels {peanut, peanuts, nuts}.
- `tree_nut`: the title module's species list + `nutella`, +
  `chestnut` (with water suppression). Satisfiers same + labels
  {tree nut, nuts}.
- `dairy`: triggers butter, milk, buttermilk, ghee, cheese, cheddar,
  mozzarella, parmesan, parmigiano, pecorino, ricotta, feta, brie,
  mascarpone, yogurt, yoghurt, + the multiword creams above.
  Satisfiers: same terms WITHOUT the plant-milk/nut-butter suppressions
  (lenient), + `margarine` and `shortening` as butter-satisfiers
  (recipes routinely list margarine and say "butter" — live in Prize
  Butter Tarts), + labels {dairy, milk}.
- `wheat_gluten`: triggers bread, flour, pasta, spaghetti, macaroni,
  linguine, fettuccine, lasagna, noodle, wheat, cracker, biscuit,
  tortilla, pastry, dumpling, crouton, couscous, bulgur, semolina,
  phyllo, filo, pita, bagel, bran, barley, rye, malt, seitan,
  `soy sauce` (phrase; triggers wheat AND soy, matching the engine's
  4bf2377 stance), breaded, floured. Satisfiers: same + `dough`, `mix`
  (rows like "cake mix"), + labels {wheat, gluten}.
- `egg`: triggers egg, eggs, meringue. Satisfiers: egg(s), meringue +
  labels {egg, eggs}. (`\begg\b` correctly matches
  "egg-yolks"/"egg wash", correctly ignores "eggplant".)
- `fish`: triggers bare `fish` (NEW), salmon, tuna, cod, halibut,
  trout, snapper, anchovy/anchovies, sardine(s), mackerel, herring,
  haddock, flounder, `sea bass`, worcestershire, puttanesca. `sole`
  deliberately omitted (homograph, no corpus benefit — match the title
  module's omission). Satisfiers: substring `fish` on rows (so
  swordfish/catfish/whitefish rows satisfy) + species + labels
  {fish, seafood}.
- `crustacean` / `mollusk` / `sesame` / `soy`: the title module's lists
  (crabmeat/crab meat included as satisfiers; scallop is safe —
  `\bscallop\b` does not match "scalloped").
- `meat` (NEW): triggers = flesh words only: bacon, beef, chicken,
  chorizo, duck, goose, ham, hot dog, lamb, pancetta, pepperoni, pork,
  prosciutto, rabbit, sausage, steak, turkey, veal. NOT
  gelatin/marshmallow/worcestershire/suet/lard (different hazard
  classes; gelatin + worcestershire are fish-side; bare `meat` is
  Tier C). Satisfiers: any flesh word OR any fish/crustacean/mollusk
  term — a row already containing any animal flesh makes the recipe
  non-vegetarian at serve time, so an additional hidden meat adds no
  incremental engine-visible hazard; only rows with NO animal-flesh
  rows at all flag (this catches "Chinese Beef and Broccoli" — zero
  flesh rows, instructions say steak/beef — while not flagging
  surf-and-turf rows that list the shrimp). Add a drift test: module's
  meat trigger set ⊇ the flesh-word subset of `MEAT_ALIASES`.
- Word-boundary notes already verified: `\bbeef\b` does not match
  "beefsteak tomato"; `\bham\b` does not match "graham"; `\bwheat\b`
  does not match "buckwheat".

## 3. Decision rule + over-quarantine guard (all numbers pre-registered blind)

**Decision rule:** a row is quarantined iff it has ≥1 un-suppressed
Tier A or Tier B category mention whose category is unsatisfied. One is
enough — no count thresholds. Tier C mismatches go to the report only.
Tier assignment is fixed by the vocabulary above, never by results.

**Guard bands (corpus = 4,045 rows):**

- Expected combined Tier A+B quarantine fraction: **1%–10%**.
- **Hard ceiling: 12% (486 rows). Above it: HALT, write nothing**,
  analyze FP classes in the dry-run report, add suppressions (each with
  a cited real example), re-run. Maximum two revision rounds; if still
  >12%, **HUMAN GATE** — the corpus is majority-defective for safety
  purposes and replacing/re-importing it is a product decision.
- **Floor sanity: <10 rows flagged = probable bug** (the three
  still-in-corpus planted faults alone guarantee ≥3; the review's
  6-of-9 sampled corruption rate makes a near-zero result implausible).
  Investigate before writing.
- **Sample audit (before any write, after guard bands pass):**
  stratified random sample of flagged rows, **n=40** (or all if fewer),
  **RNG seed 20260717**, proportional by category with min 3 per
  non-empty category. Auditor: orchestrator writes per-row
  adjudication-style evidence (quoted step, full ingredient-name list,
  category, verdict CORRECT_QUARANTINE or FALSE_POSITIVE with citable
  reason). Reviewer: advisor, as part of the mandatory FULL TREATMENT
  review. **Acceptance: ≤2/40 false positives (≥95% precision).** On
  breach: cited suppression fix, full re-run, fresh sample with seed
  20260718 (increment per round).
- **Miss spot-check:** 15 random UNflagged rows, seed 20260717 —
  orchestrator reads their instructions for any Tier A/B-class omission
  the check should have caught. Acceptance: **0 misses**. A miss is a
  spec bug (fix and re-run), not an acceptance judgment call.

## 4. Validation / test plan

New test file `tests/test_instructions_ingredient_integrity.py`,
fixtures copied verbatim from the quarantine sidecar payloads / corpus
(frozen as test fixtures so tests don't depend on live data files):

**Planted-fault (must flag, with the expected category asserted):**
- imp_348d24dd1f4d5284 Prize Butter Tarts → wheat (`pastry`,
  `pastry dough`; pecans present so the negated "without the raisins or
  nuts" step must NOT be needed to pass)
- imp_6ab74a6c238451a3 Banana-Nut Muffins → nut (`Mix nuts with flour`;
  the `ground nutmeg` row must NOT satisfy)
- imp_78c1d567c07b545a Chinese Beef and Broccoli → meat (`steak`/`beef`)
- imp_997819df41245ec6 Perfectly Spiced Banana Bread → tree_nut
  (`almonds`; the "Omit almonds" step suppressed, the "Add … almonds"
  step flags)
- imp_9e0a542fc2195d5b Bananas Baked With Custard → wheat (`bread`)
- imp_9ff0ac08d2b353ca Banana Bran Muffins → nut (`Stir in bran and
  nuts`; `pastry blender` suppressed as a tool; butter satisfied by
  rows)
- imp_ffba7239b17c5b29 Spicy Fish Cakes → fish (`Cut the fish` — no
  serving cue in that step)
- imp_d34a2ab621245cba Unusual Chicken → egg AND peanut/nut (`beaten
  egg`, `ground nut oil`) — still in corpus; resolves review finding 4
- imp_acd7c3ec0ed35a51 Rice/Apple/Raisin Dressing → Tier B stock —
  resolves review finding 3
- imp_ece8c7dd17b95468 Dirty Rice → Tier B stock (`Add the stock or
  water` — the water-alternative does NOT suppress; pork row satisfies
  meat)

**Must-NOT-flag:**
- imp_e8b6568570965387 Fish Marinade (serving-cue suppression)
- imp_f9cc221553155bfc Mallow Topped Sweet Potatoes (orange-juice
  omission is out of scope — this test documents the boundary)
- Seeds r_007, r_009, r_012 from `sample_recipes.jsonl` (r_007's
  coconut-milk instructions must not fire dairy)
- Synthetic units: nutmeg/doughnut/butternut/coconut in instructions
  with no nut rows; "cream the butter and sugar" with butter row;
  "grease and flour the pan" WITH flour row; "coconut milk" row
  satisfying a bare "milk" mention; "margarine" row satisfying "melt
  the butter"; "rice flour" row satisfying "add the flour"; "stock pot"
  phrase; "scalloped potatoes"; only-negated-mention case ("omit
  walnuts" as sole mention) not flagging.

**Structural tests:** meat set ⊇ flesh-word subset of `MEAT_ALIASES`;
import-ban test asserting the module imports no LLM/provider modules
(mirror `tests/test_safety_judge_import_ban.py`) — this makes the "no
LLM in the decision path" invariant executable; idempotency (re-run on
cleaned corpus yields 0 flags); quarantine-record shape matches the
sidecar schema. Also: the check must be structurally incapable of
reading `sample_recipes.jsonl` — seeds are protected by input scoping,
not by passing the check.

## 5. Placement and artifacts

- **Module:** `app/services/corpus_import/instructions_ingredient_integrity.py`
  — single source of truth, mirroring the title module's structure
  (vocab tables with per-entry citations,
  `find_instructions_ingredient_mismatches(recipe) -> list[Mismatch]`,
  `build_quarantine_record` with
  `check="instructions_ingredient_integrity"`, evidence including
  category, tier, matched term, and the FULL quoted step text per
  match).
- **Audit script:** `scripts/audit_instructions_integrity.py` —
  corpus-wide dry-run/report, enforces the guard bands (exits nonzero
  on ceiling/floor breach), emits the sample-audit candidate list
  (seeded selection) so the orchestrator adjudicates from a
  deterministic artifact.
- **Quarantine integration:** extend
  `scripts/quarantine_flagged_recipes.py` with
  `--check {title,instructions}` (default `title`, fully backward
  compatible); the instructions mode reuses the existing merge-by-id /
  first-decision-wins / atomic-write path untouched.
- **Import pipeline:** wire the check into `CorpusImportPipeline`
  (same pattern as the title check) so future imports are screened at
  ingest.
- **Report artifacts (committed):**
  `data/evaluation/instructions_integrity_report_<UTCstamp>.md`
  (summary counts, per-category counts, guard-band verdicts, Tier C
  table, revisions section) + a machine-readable `.json` with per-row
  evidence (recipe_id, title, tier, category, term, quoted step,
  ingredient names). Sample-audit record as a separate
  adjudication-style md, advisor-reviewed.

## 6. Downstream

Run order after APPROVED review: apply quarantine → commit
corpus+sidecar+reports → `pytest` →
`python scripts/evaluate_demo_set.py` (must hold 0.000) →
`python scripts/run_safety_benchmark.py` k=3 → fresh adjudication of
every judge flag per convention → advisor review of that adjudication →
only then any gate claim.

- **Retrieval-eval baseline (docs/phase-1.5-closeout.md, 4,263-row
  corpus): honest annotation, NOT regeneration.** Add a dated note that
  the corpus was reduced by this quarantine on 2026-07-17 and the
  pinned numbers are not comparable to post-quarantine runs; put
  regeneration in `docs/BACKLOG.md` with the corpus sizes and file
  paths. Regenerating now is ship-delaying polish.
- **Chroma: confirmed.** `load_corpus()` reads `imported_recipes.jsonl`
  directly and `RecipeRetriever.retrieve()` drops ids absent from it,
  so stale embeddings are unservable the moment the file is rewritten;
  deleting them stays a backlogged rebuild task.

## Known risks (accepted, stated)

1. **Residual misses are certain, by design.** Precision-first
   suppressions (serving cues, negation, Tier C) mean some genuinely
   incomplete rows survive; a future serve of one is adjudicated TRUE
   and the gate honestly fails. That is the correct failure mode — the
   alternative (aggressive quarantine) fails the guard and guts
   retrieval. The miss spot-check and the benchmark itself are the
   backstops.
2. **The serving-cue list can hide a real hazard** ("serve with the
   peanut sauce" where the sauce is hidden). Accepted: cue list is
   narrow, step-local, and matches in other steps still flag; the
   sample audit reviews suppression behavior on real rows.
3. **The blind bands may be wrong.** If real corruption is, say, 14%,
   the ceiling halts a correct result — that halt is intentional: at
   that fraction, corpus replacement is a human product decision, not
   an automated purge.
4. **Vocabulary hand-authoring is fallible.** Mitigated by the
   citation-per-entry convention, the drift test against
   `MEAT_ALIASES`, and the two-sided sample audits — not eliminated.

## NEEDS HUMAN (conditional)

(a) If the quarantine fraction exceeds 12% after two revision rounds,
corpus replacement/re-import is a human decision. (b) The two
pre-registered adjudication conventions (generic-oil and
orange-juice-class omissions = affirmatively-written JUDGE_FP-eligible)
are surfaced to the human before the next gate run.
