# pgvector vs Chroma retrieval parity — ROADMAP 5.2

`scripts/evaluate_retrieval.py` run twice against the identical 10,011-recipe
corpus (`scripts/ingest_recipes.py` / `scripts/seed_pgvector.py`,
`EMBEDDING_PROVIDER=hash` both times, 67 pinned eval queries), once per
`VECTOR_BACKEND`. Both use an HNSW index (`hnsw:space: cosine` in Chroma,
`vector_cosine_ops` in pgvector — see `alembic/versions/
0002_pgvector_recipe_embeddings.py`), so both are approximate-nearest-
neighbor, not exact — a small amount of tie-breaking variance between them
is expected, not a bug.

## Semantic-arm Recall@10, per category

| Category | n | Chroma | pgvector | Δ |
|---|---|---|---|---|
| cuisine | 5 | 0.1187 | 0.1187 | 0.00 |
| dietary | 5 | 0.1667 | 0.2000 | 3.33 pt |
| dish | 10 | 0.0023 | 0.0023 | 0.00 |
| ingredient | 25 | 0.0622 | 0.0739 | 1.17 pt |
| meal_type | 5 | 0.0033 | 0.0033 | 0.00 |
| paraphrase_oov | 9 | 0.0138 | 0.0138 | 0.00 |
| paraphrase_syn | 8 | 0.0000 | 0.0069 | 0.69 pt |
| **Aggregate (all 67 queries)** | 67 | **0.0469** | **0.0546** | **0.77 pt** |

## Reading this honestly

4 of 7 categories are bit-identical between backends. The two categories
with a delta over 1 point (`dietary`, n=5; `ingredient`, n=25) are exactly
the ones where a single query flipping rank order moves the metric the
most (1/5 = 20-point granularity at n=5) — consistent with HNSW tie-
breaking on near-equidistant hash-embedding vectors, not a systematic
quality gap favoring either backend (pgvector is actually slightly *ahead*
on both). The **aggregate Recall@10 delta is 0.77 points, inside the
acceptance criterion's 1-point bar**; per-category deltas at small n are
reported here rather than hidden, per this project's "never collapse an
inconvenient number to make a gate look cleaner" convention (see
CLAUDE.md's release-gate semantics for the safety benchmark, same spirit
applied here).

Neither run passes the pre-existing hash-embedding retrieval gate
(`GATE RESULT: FAIL` in both raw outputs) — that gate measures semantic-
vs-keyword quality with `EMBEDDING_PROVIDER=hash` (a deterministic fallback
with no real semantic signal, documented as gate-failing before this step
too) and is unrelated to backend choice; it would fail identically on
either backend and is not what this comparison is evaluating.

## Reproduce

```bash
EMBEDDING_PROVIDER=hash python scripts/evaluate_retrieval.py                 # chroma (default)

VECTOR_BACKEND=pgvector DATABASE_URL=postgresql://... EMBEDDING_PROVIDER=hash \
  python scripts/evaluate_retrieval.py                                      # pgvector
```
