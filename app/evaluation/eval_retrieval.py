"""Retrieval-quality evaluation: semantic (vector store/RAG) vs. keyword
baseline vs. the production hybrid path (`RecipeRetriever.retrieve()`).

Methodology (see scripts/evaluate_retrieval.py for the CLI entrypoint and the
printed methodology note, which is the canonical description of the gate):

- Each query in data/retrieval_eval_queries.jsonl carries a frozen/pinned
  `relevant_recipe_ids` ground-truth set, computed once by
  scripts/gen_retrieval_eval_queries.py (see that script's docstring) against
  the item-4-final corpus and checked in, so re-running this eval later
  always scores against the same ground truth even if the corpus changes.
- The SEMANTIC path queries the configured `VectorStore` backend directly
  (`app.rag.vector_store.get_vector_store().query(...)`, Chroma or pgvector
  per `VECTOR_BACKEND` -- see ROADMAP 5.2) with the query's free-text
  `description` -- this is RAG's core advantage: it can consume an
  unstructured user query. It over-fetches (`limit * OVERFETCH_FACTOR`) and
  then filters the returned ids down to the eval corpus universe
  (`_eval_corpus_ids()`, i.e. `{r.recipe_id for r in load_corpus()}`) BEFORE
  truncating to `limit` -- this exactly mirrors what production
  `RecipeRetriever.retrieve()` does (`store.query(..., n_results=limit*3)`
  then filter to `recipe_id in recipes_by_id`). Without this filter, raw
  vector-store results also surface `user_*` saved-library recipes indexed by
  earlier `/library/reindex` runs -- ids that are outside both
  `load_corpus()` and every query's pinned ground truth -- which occupied top
  semantic ranks and were scored as misses. That made the semantic arm
  strictly harsher than what a real user of `retrieve()` experiences, and was
  a measurement bug, not a finding about embedding quality.
- The KEYWORD baseline calls `RecipeRetriever.keyword_search` -- the actual
  production keyword-fallback path -- with the query's structured
  `ingredients` / `cuisine_preference` / `meal_type` fields, since that is
  what keyword_search's ingredient/cuisine/meal_type matching is built to
  consume. It has no free-text/title matching capability; where a query's
  structured fields are empty or off-target, that is a genuine limitation of
  the keyword path, not a modeling artifact. NOTE: for the `ingredient`,
  `cuisine`, and `meal_type` categories, `keyword_search` literally
  implements the same predicate `gen_retrieval_eval_queries.py` used to build
  ground truth (ingredient-membership / exact cuisine / exact meal_type), so
  keyword's near-1.0 score there is an ORACLE UPPER BOUND, not evidence
  keyword search "works" in the way semantic search generalizing to
  paraphrases would be a finding. `gen_retrieval_eval_queries.py`'s ground
  truth for these three categories uses its OWN strict local predicate
  (word-boundary token containment, not `ingredient_matches`) -- see that
  script's docstring -- but `keyword_search` production code is unchanged, so
  the oracle-upper-bound relationship still holds by construction. See
  scripts/evaluate_retrieval.py's methodology note.
- The HYBRID path calls `RecipeRetriever.retrieve()` itself (semantic query
  + metadata `where` filter + automatic keyword fallback when semantic
  returns fewer than `limit` results) with `user_id=None`, i.e. base-corpus
  only, matching the eval corpus universe automatically since `retrieve()`
  already filters to its own `recipes_by_id`.
- All three paths request the top `max(k_values)` results; metrics are
  computed per query per method for every k in `k_values` (recall@k, nDCG@k)
  plus MRR (independent of k).

The LLM plays no role anywhere in this module -- it is pure retrieval
(embeddings + Chroma nearest-neighbor / deterministic keyword scoring), never
a safety or nutrition decision.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.evaluation.retrieval_metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from app.rag.loaders import load_corpus
from app.rag.vector_store import get_vector_store
from app.services.recipe_retriever import RecipeRetriever, build_metadata_filter
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_QUERIES_PATH = Path(__file__).resolve().parent / "data" / "retrieval_eval_queries.jsonl"

METHODS = ("semantic", "keyword", "hybrid")

# Matches production RecipeRetriever.retrieve()'s `n_results=limit * 3` so the
# semantic arm over-fetches by the same margin before universe-filtering.
OVERFETCH_FACTOR = 3


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


@lru_cache(maxsize=1)
def _eval_corpus_ids() -> frozenset[str]:
    """The eval corpus universe: every recipe id `load_corpus()` returns.

    This is the same universe `relevant_recipe_ids` ground truth is built
    against (scripts/gen_retrieval_eval_queries.py) and the same universe
    production `RecipeRetriever.retrieve()` filters Chroma results down to
    via its `recipes_by_id` dict. The raw Chroma collection can contain
    additional `user_*` saved-library ids from earlier `/library/reindex`
    runs that are outside this universe -- see `semantic_search_ids`.
    """
    return frozenset(recipe.recipe_id for recipe in load_corpus())


def semantic_search_ids(
    query: RetrievalEvalQuery, limit: int, corpus_ids: frozenset[str] | None = None
) -> list[str]:
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

    Over-fetches `limit * OVERFETCH_FACTOR` candidates from Chroma, then
    filters the returned ids down to the eval corpus universe BEFORE
    truncating to `limit` -- exactly mirroring what `RecipeRetriever.retrieve()`
    does with its own `recipes_by_id` filter. Without this, `user_*`
    saved-library ids indexed by earlier reindex runs (which are outside the
    eval corpus and outside every query's ground truth) occupy top semantic
    ranks and get scored as misses, making this arm strictly harsher than
    the production semantic path it's meant to measure.
    """
    store = get_vector_store()
    if store.count() == 0:
        return []
    where = build_metadata_filter(query.cuisine_preference, query.meal_type)
    universe = corpus_ids if corpus_ids is not None else _eval_corpus_ids()
    raw_ids = store.query(query.description, n_results=limit * OVERFETCH_FACTOR, where=where)
    return [recipe_id for recipe_id in raw_ids if recipe_id in universe][:limit]


def keyword_search_ids(retriever: RecipeRetriever, query: RetrievalEvalQuery, limit: int) -> list[str]:
    recipes = retriever.keyword_search(
        query.ingredients,
        cuisine_preference=query.cuisine_preference,
        meal_type=query.meal_type,
        limit=limit,
    )
    return [recipe.recipe_id for recipe in recipes]


def hybrid_search_ids(retriever: RecipeRetriever, query: RetrievalEvalQuery, limit: int) -> list[str]:
    """The actual production retrieval path: `RecipeRetriever.retrieve()`
    (semantic query + metadata filter, falling back to/mixing in keyword
    results when semantic returns fewer than `limit` hits). `user_id=None`
    and `include_user_recipes=False` keep this scoped to the base corpus --
    the same universe as `load_corpus()` / the eval's ground truth -- since
    `retrieve()` already filters Chroma hits down to its own
    `recipes_by_id`, no separate universe filter is needed here.
    """
    recipes = retriever.retrieve(
        query.ingredients,
        cuisine_preference=query.cuisine_preference,
        meal_type=query.meal_type,
        limit=limit,
        user_id=None,
        include_user_recipes=False,
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
    """Run every query through all three methods and return per-query + aggregate rows.

    Returns {"per_query": [...], "aggregate": {"semantic": {...}, "keyword": {...},
    "hybrid": {...}}}.
    """
    queries = queries if queries is not None else load_eval_queries()
    k_values = k_values or [5, 10]
    top_k = max(k_values)
    retriever = retriever or RecipeRetriever()
    corpus_ids = _eval_corpus_ids()

    per_query: list[dict[str, object]] = []
    for query in queries:
        relevant_ids = set(query.relevant_recipe_ids)
        semantic_ids = semantic_search_ids(query, top_k, corpus_ids)
        keyword_ids = keyword_search_ids(retriever, query, top_k)
        hybrid_ids = hybrid_search_ids(retriever, query, top_k)

        per_query.append(
            {
                "query_id": query.query_id,
                "category": query.category,
                "num_relevant": len(relevant_ids),
                "semantic": _score_ranked_list(semantic_ids, relevant_ids, k_values),
                "keyword": _score_ranked_list(keyword_ids, relevant_ids, k_values),
                "hybrid": _score_ranked_list(hybrid_ids, relevant_ids, k_values),
            }
        )

    aggregate: dict[str, dict[str, float]] = {method: {} for method in METHODS}
    metric_names = [f"recall@{k}" for k in k_values] + [f"ndcg@{k}" for k in k_values] + ["mrr"]
    for method in METHODS:
        for metric in metric_names:
            values = [row[method][metric] for row in per_query]
            aggregate[method][metric] = sum(values) / len(values) if values else 0.0

    return {"per_query": per_query, "aggregate": aggregate, "k_values": k_values}
