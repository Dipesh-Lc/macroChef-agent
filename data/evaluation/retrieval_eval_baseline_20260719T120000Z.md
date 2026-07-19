# Retrieval evaluation re-baseline — post diet_023 cure (final A1 corpus)

**NOTE: corpus generation changed again since the prior re-baseline
(`retrieval_eval_baseline_20260719T104216Z.md`, corpus generation
`20260719T080937Z`) — this run is against the diet_023-cure corpus
generation `20260719T111906Z` + the 6-id manual quarantine (brand-cereal
rows), 3,853 active + 25 seeds = 3,878 indexed; 379 quarantined. NOT
comparable to the prior pinned baseline in `docs/phase-1.5-closeout.md`
§4, nor to the intermediate `20260719T104216Z` re-baseline (a 6-recipe
difference: those 6 were active then, quarantined now).**

- Run: `python scripts/evaluate_retrieval.py`, 2026-07-19T12:00Z (post
  diet_023 cure + manual quarantine of 6 brand-cereal rows).
- Chroma collection size: **3,878 recipes** (matches the reindex
  performed earlier in this same closing sequence: 3,853 active + 25
  seeds, 0 collisions, verified via `collection_count()` == `len(load_corpus())`).
- 67 pinned queries, k values [5, 10]. Methodology/gate definition
  unchanged.

## Per-category results

| category | note | semantic MRR | keyword MRR | hybrid MRR |
|---|---|---|---|---|
| cuisine | oracle, not gated | 1.0000 | 1.0000 | 1.0000 |
| dietary | **GATED** | 0.2667 | 0.0000 | 0.1000 |
| dish | **GATED** | 0.9000 | 0.4443 | 0.6075 |
| ingredient | oracle, not gated | 0.5397 | 0.9133 | 0.5800 |
| meal_type | oracle, not gated | 0.8667 | 1.0000 | 0.8667 |
| paraphrase_oov | reference, never gated | 0.4444 | 0.3048 | 0.3194 |
| paraphrase_syn | regression check, not gated | 0.2210 | 0.6146 | 0.2500 |

Reference-only unweighted aggregate (NOT the gate): recall@10 semantic
0.3401 / keyword 0.4557 / hybrid 0.3134; MRR semantic 0.5810 / keyword
0.6707 / hybrid 0.5266.

## Gate result

```
[WIN ] semantic vs keyword -- dish      MRR 0.9000 vs 0.4443 | Recall@10 0.6855 vs 0.2852
[WIN ] semantic vs keyword -- dietary   MRR 0.2667 vs 0.0000 | Recall@10 0.4000 vs 0.0000
[OK  ] hybrid tolerance -- dish      hybrid MRR 0.6075 vs best-of-single 0.9000 (tolerance 0.40)
[OK  ] hybrid tolerance -- dietary   hybrid MRR 0.1000 vs best-of-single 0.2667 (tolerance 0.40)

GATE RESULT: PASS
```

Both gated categories (dish, dietary) pass both criteria. Minor movement
from the prior `104216Z` re-baseline (dietary recall@5 0.30→0.40,
recall@10 0.30→0.40) — expected: the 6 quarantined brand-cereal recipes
shifted the corpus's embedding-nearest-neighbor structure slightly; the
gate result and win/OK verdicts are unchanged either way.
