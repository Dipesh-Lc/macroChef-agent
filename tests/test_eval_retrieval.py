import pytest

from app.evaluation import eval_retrieval as eval_retrieval_module
from app.evaluation.eval_retrieval import (
    RetrievalEvalQuery,
    keyword_search_ids,
    load_eval_queries,
    run_retrieval_eval,
    semantic_search_ids,
)
from app.rag.chroma_client import collection_count
from app.services.recipe_retriever import RecipeRetriever


def test_load_eval_queries_has_50_queries_with_pinned_nonempty_ground_truth() -> None:
    queries = load_eval_queries()

    assert len(queries) == 50
    for query in queries:
        assert query.relevant_recipe_ids, f"{query.query_id} has an empty ground-truth set"

    categories = {query.category for query in queries}
    assert categories == {"ingredient", "dish", "cuisine", "meal_type", "dietary"}


def test_run_retrieval_eval_computes_aggregate_from_per_query_rows(monkeypatch) -> None:
    """Isolated unit test of the aggregation logic: fake both retrieval
    methods with known ranked lists so expected Recall@k/MRR/nDCG@k values
    can be hand-computed, independent of Chroma/corpus availability."""

    queries = [
        RetrievalEvalQuery(
            query_id="q1",
            category="ingredient",
            description="test query 1",
            relevant_recipe_ids=["r1", "r2"],
        ),
        RetrievalEvalQuery(
            query_id="q2",
            category="ingredient",
            description="test query 2",
            relevant_recipe_ids=["r3"],
        ),
    ]

    def fake_semantic(query, limit):
        # q1: perfect top-2 hit. q2: relevant item at rank 1.
        return {"q1": ["r1", "r2", "rX"], "q2": ["r3", "rY"]}[query.query_id]

    def fake_keyword(retriever, query, limit):
        # q1: no hits at all. q2: relevant item at rank 2.
        return {"q1": ["rX", "rY"], "q2": ["rY", "r3"]}[query.query_id]

    monkeypatch.setattr(eval_retrieval_module, "semantic_search_ids", fake_semantic)
    monkeypatch.setattr(eval_retrieval_module, "keyword_search_ids", fake_keyword)

    class DummyRetriever:
        pass

    result = run_retrieval_eval(queries, k_values=[2], retriever=DummyRetriever())

    # q1 semantic: both relevant found in top 2 -> recall@2 = 1.0, MRR = 1.0 (rank 1)
    # q2 semantic: 1/1 relevant found -> recall@2 = 1.0, MRR = 1.0 (rank 1)
    assert result["aggregate"]["semantic"]["recall@2"] == 1.0
    assert result["aggregate"]["semantic"]["mrr"] == 1.0

    # q1 keyword: 0 hits -> recall@2 = 0.0, MRR = 0.0
    # q2 keyword: 1/1 relevant found at rank 2 -> recall@2 = 1.0, MRR = 0.5
    assert result["aggregate"]["keyword"]["recall@2"] == 0.5
    assert result["aggregate"]["keyword"]["mrr"] == 0.25

    assert len(result["per_query"]) == 2
    assert result["per_query"][0]["query_id"] == "q1"


@pytest.mark.skipif(collection_count() == 0, reason="Chroma collection not populated")
def test_semantic_and_keyword_paths_both_return_real_recipe_ids_for_a_known_query() -> None:
    """Real integration smoke test against the indexed corpus (skipped if the
    Chroma collection hasn't been built yet -- see scripts/ingest_recipes.py).
    Confirms both retrieval methods actually run end-to-end and return
    recipe ids for one of the pinned ground-truth queries; the full
    quality comparison lives in scripts/evaluate_retrieval.py."""
    queries = {q.query_id: q for q in load_eval_queries()}
    query = queries["ing_01"]  # "chicken breast and mushroom"
    retriever = RecipeRetriever()

    semantic_ids = semantic_search_ids(query, limit=10)
    keyword_ids = keyword_search_ids(retriever, query, limit=10)

    assert semantic_ids, "semantic path returned no results for a query with known relevant recipes"
    assert keyword_ids, "keyword path returned no results for a query with known relevant recipes"
    assert set(semantic_ids) & set(query.relevant_recipe_ids), (
        "semantic path did not surface any known-relevant recipe in the top 10"
    )
