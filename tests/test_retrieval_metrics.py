from app.evaluation.retrieval_metrics import ndcg_at_k, recall_at_k, reciprocal_rank


def test_recall_at_k_counts_hits_in_top_k_only():
    ranked = ["a", "b", "c", "d", "e"]
    relevant = {"c", "z"}  # "z" is never retrieved

    assert recall_at_k(ranked, relevant, k=3) == 0.5  # only "c" found in top 3
    assert recall_at_k(ranked, relevant, k=1) == 0.0
    assert recall_at_k(ranked, relevant, k=10) == 0.5  # "z" still never appears


def test_recall_at_k_empty_relevant_set_is_zero_not_divide_by_zero():
    assert recall_at_k(["a", "b"], set(), k=5) == 0.0


def test_reciprocal_rank_first_hit_position():
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == 0.5
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0
    assert reciprocal_rank(["a", "b", "c"], {"z"}) == 0.0


def test_ndcg_at_k_perfect_ranking_is_one():
    ranked = ["a", "b", "c"]
    relevant = {"a", "b"}
    assert ndcg_at_k(ranked, relevant, k=2) == 1.0


def test_ndcg_at_k_worse_ranking_scores_lower_than_perfect():
    relevant = {"a", "b"}
    perfect = ndcg_at_k(["a", "b", "c"], relevant, k=3)
    worse = ndcg_at_k(["c", "a", "b"], relevant, k=3)
    assert worse < perfect


def test_ndcg_at_k_no_hits_is_zero():
    assert ndcg_at_k(["x", "y"], {"z"}, k=2) == 0.0
