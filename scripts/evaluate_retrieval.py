"""RAG (semantic/Chroma) vs. keyword baseline vs. production hybrid
(`RecipeRetriever.retrieve()`) retrieval-quality evaluation.

Runs the pinned queries in app/evaluation/data/retrieval_eval_queries.jsonl
through all three retrieval paths and reports Recall@k, nDCG@k, and MRR for
each, broken down per category. See app/evaluation/eval_retrieval.py for the
full methodology docstring (how each method consumes a query, why ground
truth is frozen/pinned rather than recomputed live, and the universe-filter
fix that keeps the semantic arm apples-to-apples with production).

Determinism note: EMBEDDING_PROVIDER=local uses sentence-transformers
(all-MiniLM-L6-v2) running on CPU in eval (no GPU nondeterminism) with no
sampling involved in either encoding or Chroma's nearest-neighbor query, so
results are deterministic run-to-run for a fixed corpus + fixed Chroma index.
The one source of run-to-run variation is if the Chroma collection has been
rebuilt in between (e.g. a corpus re-import) -- pin your corpus/index state
before comparing eval numbers across time.

METHODOLOGY NOTE -- read before interpreting the numbers below:

1. There is no single weighted "aggregate" headline number here. The 62
   pinned queries are NOT sampled from real usage (no usage data exists
   pre-launch) -- their category mix (25 ingredient / 10 dish / 5 cuisine /
   5 meal_type / 5 dietary / 12 paraphrase) is an arbitrary authoring choice,
   so an unweighted average over them would silently encode that choice as
   if it were a claim about real query distribution. The PER-CATEGORY table
   is the headline; an unweighted all-query aggregate is printed below it
   purely as a reference figure, explicitly marked as not the gate.

2. `keyword_search` (app/services/recipe_retriever.py) directly implements
   the SAME predicate used to build ground truth for the `ingredient`,
   `cuisine`, and `meal_type` categories (ingredient-membership match / exact
   cuisine match / exact meal_type match -- see
   scripts/gen_retrieval_eval_queries.py). Keyword's near-1.0 score on those
   three categories is therefore an ORACLE UPPER BOUND -- "does the
   label-generating predicate match itself" -- not a finding about keyword
   search quality on real queries. The `dish` (title match), `dietary`
   (diet-tag match), and `paraphrase` (canonical-ingredient match paired with
   colloquial/synonym query text) categories are genuinely
   METHOD-INDEPENDENT: their ground truth does not share logic with either
   the semantic or the keyword path, so those are the meaningful comparison
   categories.

3. `cuisine` and `dietary` ground truth is seed-only: `cuisine`, `meal_type`,
   and `diet_tags` metadata are populated on the 25 hand-curated seed recipes
   but almost entirely absent on the ~4,238 imported Food.com recipes (corpus
   metadata sparsity). BACKLOG: an ML auto-tagger is a candidate to backfill
   this metadata at scale, but per CLAUDE.md it would be advisory-only
   (suggest/rank tags) and must NEVER feed the deterministic allergy/diet
   safety filter (app.services.constraint_engine).

GATE DEFINITION (see `_run_gate` below):
  (i)  semantic CLEARLY beats keyword (strictly higher MRR AND strictly
       higher Recall@10) on every METHOD-INDEPENDENT category: dish,
       paraphrase, dietary.
  (ii) hybrid >= keyword (both MRR and Recall@10, non-strict) on EVERY
       category, including the oracle ones -- hybrid must never regress
       below the keyword floor anywhere.
Both conditions must hold for a PASS.

Usage: python scripts/evaluate_retrieval.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.eval_retrieval import METHODS, load_eval_queries, run_retrieval_eval  # noqa: E402
from app.rag.chroma_client import collection_count  # noqa: E402

METHOD_LABELS = {
    "semantic": "Semantic (RAG/Chroma)",
    "keyword": "Keyword baseline",
    "hybrid": "Hybrid (retrieve())",
}

METHOD_INDEPENDENT_CATEGORIES = ("dish", "paraphrase", "dietary")
ORACLE_CATEGORIES = ("ingredient", "cuisine", "meal_type")


def _print_table(title: str, aggregate: dict[str, dict[str, float]], metric_order: list[str]) -> None:
    print(f"\n=== {title} ===")
    header = f"{'metric':<12}" + "".join(f"{METHOD_LABELS[m]:>22}" for m in METHODS)
    print(header)
    for metric in metric_order:
        row = f"{metric:<12}"
        for method in METHODS:
            row += f"{aggregate[method][metric]:>22.4f}"
        print(row)


def _category_aggregate(rows: list[dict], metric_order: list[str]) -> dict[str, dict[str, float]]:
    cat_aggregate: dict[str, dict[str, float]] = {method: {} for method in METHODS}
    for method in METHODS:
        for metric in metric_order:
            values = [row[method][metric] for row in rows]
            cat_aggregate[method][metric] = sum(values) / len(values) if values else 0.0
    return cat_aggregate


def _run_gate(category_aggregates: dict[str, dict[str, dict[str, float]]]) -> bool:
    print("\n" + "=" * 78)
    print("GATE")
    print("  (i)  semantic clearly beats keyword (MRR and Recall@10 both strictly")
    print("       higher) on every METHOD-INDEPENDENT category: dish, paraphrase, dietary")
    print("  (ii) hybrid >= keyword (MRR and Recall@10, non-strict) on EVERY category")
    print("=" * 78)

    semantic_results: list[tuple[str, bool]] = []
    for category in METHOD_INDEPENDENT_CATEGORIES:
        if category not in category_aggregates:
            print(f"  [SKIP] '{category}' not present in this run's queries")
            continue
        cat = category_aggregates[category]
        wins = (
            cat["semantic"]["mrr"] > cat["keyword"]["mrr"]
            and cat["semantic"]["recall@10"] > cat["keyword"]["recall@10"]
        )
        semantic_results.append((category, wins))
        status = "WIN " if wins else "FAIL"
        print(
            f"  [{status}] semantic vs keyword -- {category:<12} "
            f"MRR {cat['semantic']['mrr']:.4f} vs {cat['keyword']['mrr']:.4f} | "
            f"Recall@10 {cat['semantic']['recall@10']:.4f} vs {cat['keyword']['recall@10']:.4f}"
        )

    hybrid_results: list[tuple[str, bool]] = []
    for category in sorted(category_aggregates):
        cat = category_aggregates[category]
        ok = (
            cat["hybrid"]["mrr"] >= cat["keyword"]["mrr"]
            and cat["hybrid"]["recall@10"] >= cat["keyword"]["recall@10"]
        )
        hybrid_results.append((category, ok))
        oracle_note = "  [oracle]" if category in ORACLE_CATEGORIES else ""
        status = "OK  " if ok else "FAIL"
        print(
            f"  [{status}] hybrid   vs keyword -- {category:<12} "
            f"MRR {cat['hybrid']['mrr']:.4f} vs {cat['keyword']['mrr']:.4f} | "
            f"Recall@10 {cat['hybrid']['recall@10']:.4f} vs {cat['keyword']['recall@10']:.4f}{oracle_note}"
        )

    gate_pass = all(wins for _, wins in semantic_results) and all(ok for _, ok in hybrid_results)
    print(f"\nGATE RESULT: {'PASS' if gate_pass else 'FAIL'}")
    return gate_pass


def main() -> int:
    count = collection_count()
    print(f"Chroma collection size: {count} recipes")
    if count == 0:
        print(
            "** Chroma collection is empty -- run scripts/ingest_recipes.py first. "
            "Semantic and hybrid scores will be 0 for every query. **"
        )

    queries = load_eval_queries()
    k_values = [5, 10]
    result = run_retrieval_eval(queries, k_values=k_values)

    metric_order = [f"recall@{k}" for k in k_values] + [f"ndcg@{k}" for k in k_values] + ["mrr"]

    print(f"\nRan {len(queries)} queries (k values: {k_values})")

    print(
        "\nSee this script's module docstring for the full methodology note "
        "(oracle-upper-bound categories, seed-only sparsity, gate definition)."
    )

    # Per-category breakdown -- this is the headline.
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in result["per_query"]:
        by_category[row["category"]].append(row)

    print("\n" + "#" * 78)
    print("# PER-CATEGORY RESULTS (headline -- see methodology note above)")
    print("#" * 78)

    category_aggregates: dict[str, dict[str, dict[str, float]]] = {}
    for category in sorted(by_category):
        rows = by_category[category]
        cat_aggregate = _category_aggregate(rows, metric_order)
        category_aggregates[category] = cat_aggregate
        label = category
        if category in ORACLE_CATEGORIES:
            label += "  [keyword = ORACLE UPPER BOUND, not a finding]"
        elif category in METHOD_INDEPENDENT_CATEGORIES:
            label += "  [method-independent -- gated]"
        _print_table(f"Category: {label} (n={len(rows)})", cat_aggregate, metric_order)

    # Unweighted aggregate over all queries, kept only as a reference figure --
    # see methodology note item 1 for why this is NOT the gate.
    _print_table(
        "Reference only -- unweighted aggregate over all queries (NOT the gate, "
        "arbitrary category mix)",
        result["aggregate"],
        metric_order,
    )

    _run_gate(category_aggregates)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
