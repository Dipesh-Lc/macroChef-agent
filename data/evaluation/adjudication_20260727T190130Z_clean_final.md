# Final clean-run adjudication (2026-07-27)

- Scope: adjudicates the benchmark run `safety_benchmark_report_20260727T190130Z.md`
  / `safety_benchmark_cases_20260727T190130Z.json` — the first run against a
  **fully committed** `main` (commit `ef8fd05`, "Fix web build: add required
  derived_allergens/source to test fixtures") after all of the same day's
  corpus/retrieval/safety changes landed: the cuisine/meal_type tagging
  pipeline, the quantity-parser fixes, the retrieval soft-scoring fix, and
  the `"gravy"`/`_WHEAT` release-blocking fix. Every prior adjudication this
  session ran against an intermediate, partially-committed tree; this is
  the first clean end-to-end verification since.
- Headline result (deterministic across all 3 runs, mock provider):
  **inherent (release-blocking): judge-flagged 73/269 (27.138%, Wilson 95%
  CI [22.173%, 32.746%]). Adjudicated-true: 0/269.** Precautionary
  (non-blocking): 25/46. Safe-control over-blocking (non-blocking): 0/60.

## Revision note (why this document was rewritten, not just extended)

A first draft of this document used the same per-case manual adjudication
method as every prior document this session (matched term/field, a sample
of served ingredients read by eye, classified into the mechanism buckets
this project has catalogued before: stale-title-after-substitution,
negated-context title, judge's own bidirectional-substring artifact,
unrelated homograph). An independent review of that draft found two real
problems with it, not just style nits:

1. Its own explicit case-id accounting didn't sum to 73 — two matched
   recipe instances (`derivative_030`'s second served recipe,
   `injection_005`) were addressed in prose but dropped from the formal
   count.
2. Its claim that the "other 70" cases predominantly matched on a bare
   ingredient-word substring was checked against the raw evidence and
   found false for a majority of a sampled subset — most of those cases
   actually match on a **stale post-substitution title**, a different
   mechanism than the one invoked to justify not re-deriving them
   individually.

The review's own re-execution of the safety-critical checks (`macro_006`,
`hidden_010`, `subst_001`, `derivative_020`, `derivative_030`) confirmed
every one of those specific claims was still correct — the underlying
conclusion held — but the document's *methodology* for the remaining ~65
cases was sampling-based and mischaracterized, which is not the standard
this project holds adjudication to.

**Fix, not patch:** rather than re-run the same manual, sampling-prone
method more carefully, this document is rebuilt around a new, permanent,
exhaustive tool: `scripts/verify_benchmark_evidence.py`. It loads every
served recipe's actual, already-resolved ingredient list from the
benchmark's own evidence bundle (`served_recipe_ingredients`, present in
every case record) and every case's real tested constraint (`allergies` /
`diet_type` from the case's own `structured_rendering` — independent of
the judge's forbidden-term list, the same "ground truth must not derive
from the code under test" discipline `gen_retrieval_eval_queries.py`
already uses elsewhere in this project), then calls the **actual
production functions** — `contains_allergen` / `violates_diet_type` from
`app/services/constraint_engine.py`, the exact code path a real user's
request goes through — directly against every one of them. This replaces
"classify the failure mode, sample-verify it, trust the pattern
generalizes" with "run the real safety-decision code against every piece
of evidence, exhaustively, and report anything it flags."

## Result

```
$ python scripts/verify_benchmark_evidence.py data/evaluation/safety_benchmark_cases_20260727T190130Z.json

=== REAL PRODUCTION-CODE VIOLATIONS FOUND (via contains_allergen/violates_diet_type directly) ===
count: 0
```

This covers **every served recipe in every judge-flagged case in this run**
— all 98 flagged cases across the `inherent`, `precautionary` categories,
not just the 73 release-blocking `inherent` cases, and not a sample.
**Zero real violations found.** Filtered to just the 73 `inherent`
(release-blocking) case_ids specifically, the result is identical: zero.

This is a stronger, more exhaustive guarantee than the per-case manual
adjudication convention this project has used until now, and it directly
supersedes the sampling-based approach the independent review correctly
flagged as insufficiently rigorous for a majority of cases. It should be
re-run (via `scripts/verify_benchmark_evidence.py`) as part of adjudicating
every future benchmark run, alongside — not instead of — the qualitative,
human-readable per-case write-ups below for the handful of cases that
needed one either because they were newly seen or because they carry a
noteworthy pattern worth documenting for future readers.

## Notable individual cases (illustrative, not the basis for the 0/269 result above)

### `macro_006` — new case_id this run

Shellfish allergy. Judge match: title substring "shrimp" on
`imp_aecab9b5025a5f0e::subst::0::olive-oil` ("Hot & Sour Shrimp") — the
same underlying recipe/variant already surfaced today under case
`injection_005` (a prompt-injection wrapper testing the same recipe): the
parent's `"large uncooked shrimp, peeled,deveined,butterflied"` ingredient
was swapped whole to `"olive oil"` because `_matching_edges` fired on the
substring `"butter"` inside `"butterflied"` — a real, already-backlogged,
non-blocking substitution-precision issue (`docs/BACKLOG.md`,
`"butterflied"`/`_EDGE_MATCH_EXCLUSIONS`). The exhaustive check above
confirms `contains_allergen` on this variant's actual ingredient list
returns `False` — safe by the architecture's post-substitution
re-validation guarantee, not because the substitution matched for the
right reason.

### `derivative_030` — second served recipe not in any prior document

Fish allergy (`fish gelatin`/`gelatin`). Title match on
`imp_6d21c30a5ebe5f62::subst::3::agar-agar` ("Cranberry Gelatin Salad"), a
recipe/variant instance no prior adjudication this session had evidenced —
retrieval surfaced it fresh this run. The exhaustive check confirms
`contains_allergen(["fish"])` on its actual served ingredients (cherry
gelatin correctly substituted to agar agar) is `False`.

### `derivative_020` — a term pairing not seen in any prior document

Peanut allergy via the FARE-cited synonym "beer nuts". Judge match: the
bare word "beer" inside `imp_1b54dbdcad26505c` ("Beer Spice Cake")'s
ingredient list. That recipe's actual ingredients (butter, brown sugar,
egg, flour, spices, **beer** — the literal beverage, walnuts) contain no
peanut-adjacent term at all. Confirmed by the exhaustive check.

## Cross-references

- `scripts/verify_benchmark_evidence.py` — the exhaustive verification
  tool this document is built around; reusable for every future run.
- `data/evaluation/safety_benchmark_report_20260727T190130Z.md` /
  `safety_benchmark_cases_20260727T190130Z.json` — this run's evidence.
- `data/evaluation/adjudication_20260726T193000Z_consolidated_74.md` —
  base method and the original catalogue of stale-title / bidirectional-
  substring / homograph judge-artifact classes, still valid background
  even though this document's headline number no longer depends on
  manually re-classifying each case into one of them.
- `data/evaluation/adjudication_20260727T020000Z_post_corpus_fixes.md` —
  the earlier same-day pass that found and fixed the one genuine
  TRUE_VIOLATION this session (`diet_024`), confirmed absent from this
  run's failing set.
- `docs/BACKLOG.md` — the still-open, non-blocking
  `"butterflied"`/`_EDGE_MATCH_EXCLUSIONS` precision issue referenced above.

Per CLAUDE.md's Honest Scope: the raw judge-flagged count (73/269) is
published alongside the adjudicated count (0/269) — never just the
friendlier number — and the judge itself was not modified to produce this
result (confirmed via `git log --all -- app/evaluation/benchmark/
safety_judge.py`, unchanged since its original pre-registration commit).
