"""RAG (semantic/Chroma) vs. keyword-baseline retrieval-quality evaluation.

Runs the 50 pinned queries in app/evaluation/data/retrieval_eval_queries.jsonl
through both retrieval methods and reports Recall@k, nDCG@k, and MRR for
each, plus a per-category breakdown. See app/evaluation/eval_retrieval.py for
the full methodology docstring (how each method consumes a query, why ground
truth is frozen/pinned rather than recomputed live).

Determinism note: EMBEDDING_PROVIDER=local uses sentence-transformers
(all-MiniLM-L6-v2) running on CPU in eval (no GPU nondeterminism) with no
sampling involved in either encoding or Chroma's nearest-neighbor query, so
results are deterministic run-to-run for a fixed corpus + fixed Chroma index.
The one source of run-to-run variation is if the Chroma collection has been
rebuilt in between (e.g. a corpus re-import) -- pin your corpus/index state
before comparing eval numbers across time.

Usage: python scripts/evaluate_retrieval.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.eval_retrieval import load_eval_queries, run_retrieval_eval  # noqa: E402
from app.rag.chroma_client import collection_count  # noqa: E402

METHOD_LABELS = {"semantic": "Semantic (RAG/Chroma)", "keyword": "Keyword baseline"}


def _print_table(title: str, aggregate: dict[str, dict[str, float]], metric_order: list[str]) -> None:
    print(f"\n=== {title} ===")
    header = f"{'metric':<12}" + "".join(f"{METHOD_LABELS[m]:>24}" for m in ("semantic", "keyword"))
    print(header)
    for metric in metric_order:
        row = f"{metric:<12}"
        for method in ("semantic", "keyword"):
            row += f"{aggregate[method][metric]:>24.4f}"
        print(row)


def main() -> int:
    count = collection_count()
    print(f"Chroma collection size: {count} recipes")
    if count == 0:
        print(
            "** Chroma collection is empty -- run scripts/ingest_recipes.py first. "
            "Semantic scores will be 0 for every query. **"
        )

    queries = load_eval_queries()
    k_values = [5, 10]
    result = run_retrieval_eval(queries, k_values=k_values)

    metric_order = [f"recall@{k}" for k in k_values] + [f"ndcg@{k}" for k in k_values] + ["mrr"]

    print(f"\nRan {len(queries)} queries (k values: {k_values})")
    _print_table("Aggregate (all 50 queries)", result["aggregate"], metric_order)

    # Per-category breakdown.
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in result["per_query"]:
        by_category[row["category"]].append(row)

    for category in sorted(by_category):
        rows = by_category[category]
        cat_aggregate = {"semantic": {}, "keyword": {}}
        for method in ("semantic", "keyword"):
            for metric in metric_order:
                values = [row[method][metric] for row in rows]
                cat_aggregate[method][metric] = sum(values) / len(values) if values else 0.0
        _print_table(f"Category: {category} (n={len(rows)})", cat_aggregate, metric_order)

    # Headline gate check.
    semantic_mrr = result["aggregate"]["semantic"]["mrr"]
    keyword_mrr = result["aggregate"]["keyword"]["mrr"]
    semantic_recall10 = result["aggregate"]["semantic"]["recall@10"]
    keyword_recall10 = result["aggregate"]["keyword"]["recall@10"]

    print("\n=== Gate: does RAG measurably beat keyword? ===")
    print(f"MRR:        semantic={semantic_mrr:.4f}  keyword={keyword_mrr:.4f}")
    print(f"Recall@10:  semantic={semantic_recall10:.4f}  keyword={keyword_recall10:.4f}")
    if semantic_mrr > keyword_mrr and semantic_recall10 > keyword_recall10:
        print("RESULT: semantic/RAG measurably beats the keyword baseline on both MRR and Recall@10.")
    else:
        print(
            "RESULT: semantic/RAG did NOT clearly beat the keyword baseline on both headline "
            "metrics. This is reported as-is -- see the per-category breakdown above for where "
            "each method wins/loses."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
