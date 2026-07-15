"""Retrieval-quality evaluation: semantic (Chroma/RAG) vs. keyword baseline.

Methodology (see scripts/evaluate_retrieval.py for the CLI entrypoint):

- Each query in data/retrieval_eval_queries.jsonl carries a frozen/pinned
  `relevant_recipe_ids` ground-truth set, computed once by
  scripts/gen_retrieval_eval_queries.py (see that script's docstring) against
  the item-4-final corpus and checked in, so re-running this eval later
  always scores against the same ground truth even if the corpus changes.
- The SEMANTIC path queries Chroma directly (`query_collection`) with the
  query's free-text `description` -- this is RAG's core advantage: it can
  consume an unstructured user query.
- The KEYWORD baseline calls `RecipeRetriever.keyword_search` -- the actual
  production keyword-fallback path -- with the query's structured
  `ingredients` / `cuisine_preference` / `meal_type` fields, since that is
  what keyword_search's ingredient/cuisine/meal_type matching is built to
  consume. It has no free-text/title matching capability; where a query's
  structured fields are empty or off-target, that is a genuine limitation of
  the keyword path, not a modeling artifact.
- Both paths request the top `max(k_values)` results; metrics are computed
  per query per method for every k in `k_values` (recall@k, nDCG@k) plus MRR
  (independent of k).

The LLM plays no role anywhere in this module -- it is pure retrieval
(embeddings + Chroma nearest-neighbor / deterministic keyword scoring), never
a safety or nutrition decision.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.evaluation.retrieval_metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from app.rag.chroma_client import collection_count, query_collection
from app.services.recipe_retriever import RecipeRetriever, build_metadata_filter
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_QUERIES_PATH = Path(__file__).resolve().parent / "data" / "retrieval_eval_queries.jsonl"


def evaluate_retrieval_smoke(query_ingredients: list[str]) -> dict[str, object]:
    retriever = RecipeRetriever()
    recipes = retriever.retrieve(query_ingredients, limit=5)
    return {"count": len(recipes), "titles": [recipe.title for recipe in recipes]}


class RetrievalEvalQuery(BaseModel):
    query_id: str
    category: str
    description: str
    ingredients: list[str] = []
    cuisine_preference: str | None = None
    meal_type: str | None = None
    relevant_recipe_ids: list[str]


def load_eval_queries(path: str | Path | None = None) -> list[RetrievalEvalQuery]:
    queries_path = Path(path) if path is not None else DEFAULT_QUERIES_PATH
    queries: list[RetrievalEvalQuery] = []
    with queries_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                queries.append(RetrievalEvalQuery.model_validate(json.loads(line)))
    return queries


def semantic_search_ids(query: RetrievalEvalQuery, limit: int) -> list[str]:
    """Rank recipe ids by Chroma cosine similarity to the query's free text,
    pre-filtered by the same cuisine/meal_type `where` metadata clause
    RecipeRetriever.retrieve() actually applies in production.

    Bypasses RecipeRetriever.retrieve()'s automatic keyword-fallback mixing
    (the `if len(semantic) < limit: ...keyword_search...` branch) so this
    measures the semantic path in isolation, not a hybrid -- but the
    metadata pre-filter itself is part of the semantic path proper (it runs
    inside the same `collection.query(..., where=...)` call before any
    fallback logic), so it's kept here for fidelity to what "the semantic
    path via RecipeRetriever" actually does.
    """
    if collection_count() == 0:
        return []
    where = build_metadata_filter(query.cuisine_preference, query.meal_type)
    return query_collection(query.description, n_results=limit, where=where)


def keyword_search_ids(retriever: RecipeRetriever, query: RetrievalEvalQuery, limit: int) -> list[str]:
    recipes = retriever.keyword_search(
        query.ingredients,
        cuisine_preference=query.cuisine_preference,
        meal_type=query.meal_type,
        limit=limit,
    )
    return [recipe.recipe_id for recipe in recipes]


def _score_ranked_list(ranked_ids: list[str], relevant_ids: set[str], k_values: list[int]) -> dict[str, float]:
    row: dict[str, float] = {}
    for k in k_values:
        row[f"recall@{k}"] = recall_at_k(ranked_ids, relevant_ids, k)
        row[f"ndcg@{k}"] = ndcg_at_k(ranked_ids, relevant_ids, k)
    row["mrr"] = reciprocal_rank(ranked_ids, relevant_ids)
    return row


def run_retrieval_eval(
    queries: list[RetrievalEvalQuery] | None = None,
    k_values: list[int] | None = None,
    retriever: RecipeRetriever | None = None,
) -> dict[str, object]:
    """Run every query through both methods and return per-query + aggregate rows.

    Returns {"per_query": [...], "aggregate": {"semantic": {...}, "keyword": {...}}}.
    """
    queries = queries if queries is not None else load_eval_queries()
    k_values = k_values or [5, 10]
    top_k = max(k_values)
    retriever = retriever or RecipeRetriever()

    per_query: list[dict[str, object]] = []
    for query in queries:
        relevant_ids = set(query.relevant_recipe_ids)
        semantic_ids = semantic_search_ids(query, top_k)
        keyword_ids = keyword_search_ids(retriever, query, top_k)

        per_query.append(
            {
                "query_id": query.query_id,
                "category": query.category,
                "num_relevant": len(relevant_ids),
                "semantic": _score_ranked_list(semantic_ids, relevant_ids, k_values),
                "keyword": _score_ranked_list(keyword_ids, relevant_ids, k_values),
            }
        )

    aggregate: dict[str, dict[str, float]] = {"semantic": {}, "keyword": {}}
    metric_names = [f"recall@{k}" for k in k_values] + [f"ndcg@{k}" for k in k_values] + ["mrr"]
    for method in ("semantic", "keyword"):
        for metric in metric_names:
            values = [row[method][metric] for row in per_query]
            aggregate[method][metric] = sum(values) / len(values) if values else 0.0

    return {"per_query": per_query, "aggregate": aggregate, "k_values": k_values}
