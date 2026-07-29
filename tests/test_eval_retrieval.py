import pytest

from app.evaluation import eval_retrieval as eval_retrieval_module
from app.evaluation.eval_retrieval import (
    RetrievalEvalQuery,
    hybrid_search_ids,
    keyword_search_ids,
    load_eval_queries,
    run_retrieval_eval,
    semantic_search_ids,
)
from app.evaluation.retrieval_metrics import reciprocal_rank
from app.rag.vector_store import get_vector_store
from app.services.recipe_retriever import RecipeRetriever


def test_load_eval_queries_has_67_queries_with_pinned_nonempty_ground_truth() -> None:
    """67 queries: 25 ingredient / 10 dish / 5 cuisine / 5 meal_type / 5
    dietary / 8 paraphrase_syn / 9 paraphrase_oov. See
    scripts/gen_retrieval_eval_queries.py's docstring for the Phase 1.5
    closeout decontamination (strict local ground-truth predicate) and the
    paraphrase_syn/paraphrase_oov split rationale."""
    queries = load_eval_queries()

    assert len(queries) == 67
    for query in queries:
        assert query.relevant_recipe_ids, f"{query.query_id} has an empty ground-truth set"

    categories = {query.category for query in queries}
    assert categories == {
        "ingredient",
        "dish",
        "cuisine",
        "meal_type",
        "dietary",
        "paraphrase_syn",
        "paraphrase_oov",
    }
    # paraphrase_syn: colloquial anchors resolvable via SYNONYMS -- a
    # synonym-table regression test, not the embedding-value test.
    assert sum(1 for q in queries if q.category == "paraphrase_syn") >= 8
    # paraphrase_oov: colloquial anchors verifiably absent from SYNONYMS/fuzzy
    # -- the true embedding-generalization test. n(oov) >= 8 per the Phase 1.5
    # closeout spec (was n=4, too thin to trust either way it lands).
    assert sum(1 for q in queries if q.category == "paraphrase_oov") >= 8


def test_run_retrieval_eval_computes_aggregate_from_per_query_rows(monkeypatch) -> None:
    """Isolated unit test of the aggregation logic: fake all three retrieval
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

    def fake_semantic(query, limit, corpus_ids=None):
        # q1: perfect top-2 hit. q2: relevant item at rank 1.
        return {"q1": ["r1", "r2", "rX"], "q2": ["r3", "rY"]}[query.query_id]

    def fake_keyword(retriever, query, limit):
        # q1: no hits at all. q2: relevant item at rank 2.
        return {"q1": ["rX", "rY"], "q2": ["rY", "r3"]}[query.query_id]

    def fake_hybrid(retriever, query, limit):
        # q1: relevant item at rank 1. q2: no hits at all.
        return {"q1": ["r1", "rX"], "q2": ["rY", "rX"]}[query.query_id]

    monkeypatch.setattr(eval_retrieval_module, "semantic_search_ids", fake_semantic)
    monkeypatch.setattr(eval_retrieval_module, "keyword_search_ids", fake_keyword)
    monkeypatch.setattr(eval_retrieval_module, "hybrid_search_ids", fake_hybrid)

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

    # q1 hybrid: 1/2 relevant found at rank 1 -> recall@2 = 0.5, MRR = 1.0
    # q2 hybrid: 0 hits -> recall@2 = 0.0, MRR = 0.0
    assert result["aggregate"]["hybrid"]["recall@2"] == 0.25
    assert result["aggregate"]["hybrid"]["mrr"] == 0.5

    assert len(result["per_query"]) == 2
    assert result["per_query"][0]["query_id"] == "q1"
    assert set(result["aggregate"]) == {"semantic", "keyword", "hybrid"}


@pytest.mark.skipif(get_vector_store().count() == 0, reason="Vector store not populated")
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


@pytest.mark.skipif(get_vector_store().count() == 0, reason="Vector store not populated")
def test_hybrid_path_returns_real_recipe_ids_for_a_known_query() -> None:
    """Smoke test for the production hybrid path (`RecipeRetriever.retrieve()`)
    as scored by the eval: it must return ids and surface at least one
    known-relevant recipe, same bar as the semantic/keyword smoke test."""
    queries = {q.query_id: q for q in load_eval_queries()}
    query = queries["ing_01"]
    retriever = RecipeRetriever()

    hybrid_ids = hybrid_search_ids(retriever, query, limit=10)

    assert hybrid_ids, "hybrid path returned no results for a query with known relevant recipes"
    assert set(hybrid_ids) & set(query.relevant_recipe_ids), (
        "hybrid path did not surface any known-relevant recipe in the top 10"
    )


@pytest.mark.skipif(get_vector_store().count() == 0, reason="Vector store not populated")
def test_semantic_search_ids_filters_to_eval_corpus_universe() -> None:
    """Regression test for the universe-mismatch bug: every id
    `semantic_search_ids` returns must be a member of the eval corpus
    (`load_corpus()`), never a `user_*` saved-library id from an earlier
    `/library/reindex` run that is outside both `load_corpus()` and every
    query's pinned ground truth."""
    corpus_ids = eval_retrieval_module._eval_corpus_ids()
    queries = {q.query_id: q for q in load_eval_queries()}
    query = queries["ing_01"]

    semantic_ids = semantic_search_ids(query, limit=10)

    assert semantic_ids, "expected at least one semantic hit for a query with known relevant recipes"
    assert set(semantic_ids) <= corpus_ids, (
        "semantic_search_ids returned an id outside the eval corpus universe -- "
        "the production-parity universe filter regressed"
    )


@pytest.mark.skipif(get_vector_store().count() == 0, reason="Vector store not populated")
def test_semantic_search_cuisine_filter_yields_perfect_mrr_by_construction() -> None:
    """Regression test for the universe-mismatch bug: under an exact-match
    cuisine `where` filter, every id Chroma returns that survives the
    eval-corpus-universe filter is, by construction, a recipe whose indexed
    `cuisine` metadata equals the query's cuisine -- and every cuisine
    query's ground truth is exactly `recipe.cuisine == <cuisine>`
    (scripts/gen_retrieval_eval_queries.py). So the first (and every)
    filtered semantic hit must be relevant, i.e. MRR == 1.0. Before the
    universe fix, unrelated `user_*` ids with no cuisine match could occupy
    top ranks and depress this to 0."""
    queries = {q.query_id: q for q in load_eval_queries()}
    query = queries["cuisine_01"]  # Mediterranean

    semantic_ids = semantic_search_ids(query, limit=10)

    assert semantic_ids, "expected at least one Mediterranean recipe in the corpus"
    relevant_ids = set(query.relevant_recipe_ids)
    assert reciprocal_rank(semantic_ids, relevant_ids) == 1.0
