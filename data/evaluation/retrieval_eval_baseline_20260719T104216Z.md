# Retrieval evaluation re-baseline — post A1 scraped-archive migration

**NOTE: corpus generation changed (scraped-archive re-import, task A1,
2026-07-19); NOT comparable to the prior pinned baseline in
`docs/phase-1.5-closeout.md` §4 (67 queries, 4,263-recipe corpus,
all-MiniLM-L6-v2) or to any intermediate baseline computed against an
earlier corpus generation. This run is against the FINAL A1 corpus (3,859
active + 25 seeds = 3,884 indexed; 373 quarantined) — see
`docs/BACKLOG.md`'s now-closed "Retrieval-eval baseline regeneration
after the 2026-07-18 mass quarantine" item, which this run also
supersedes/re-does under the new corpus.**

- Run: `python scripts/evaluate_retrieval.py`, 2026-07-19T10:42Z.
- Chroma collection size: **3,884 recipes** (matches the reindex
  performed earlier in this same closing sequence: 3,859 active +
  25 seeds, 0 collisions).
- 67 pinned queries (25 ingredient / 10 dish / 5 cuisine / 5 meal_type /
  5 dietary / 8 paraphrase_syn / 9 paraphrase_oov), k values [5, 10].
- Methodology, gate definition, and category framing unchanged from
  `app/evaluation/eval_retrieval.py` / `scripts/evaluate_retrieval.py`'s
  own module docstrings (oracle-upper-bound categories never gated,
  dish/dietary are the method-independent GATED categories, hybrid
  tolerance 0.40).

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

Reference-only unweighted aggregate over all 67 queries (NOT the gate):
recall@10 semantic 0.3327 / keyword 0.4557 / hybrid 0.3059; MRR semantic
0.5810 / keyword 0.6707 / hybrid 0.5266.

## Gate result

```
[WIN ] semantic vs keyword -- dish      MRR 0.9000 vs 0.4443 | Recall@10 0.6855 vs 0.2852
[WIN ] semantic vs keyword -- dietary   MRR 0.2667 vs 0.0000 | Recall@10 0.3000 vs 0.0000
[OK  ] hybrid tolerance -- dish      hybrid MRR 0.6075 vs best-of-single 0.9000 (tolerance 0.40)
[OK  ] hybrid tolerance -- dietary   hybrid MRR 0.1000 vs best-of-single 0.2667 (tolerance 0.40)

GATE RESULT: PASS
```

Both gated categories (dish, dietary) pass on both criteria (semantic
strictly beats keyword on MRR + Recall@10; hybrid stays within the 0.40
tolerance of the better single method). `paraphrase_syn` shows keyword
winning as expected (synonym-table regression check, reference only);
`paraphrase_oov` shows semantic winning on MRR this run (reference only,
Phase 3.5 baseline, never gated either way).

Full raw script output is not separately archived beyond this summary;
re-run `python scripts/evaluate_retrieval.py` against the current corpus
to reproduce.
