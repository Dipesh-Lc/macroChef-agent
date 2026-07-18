"""Generic ranked-list IR metrics for the retrieval eval.

Deliberately independent of any recommendation/safety logic in
`app.evaluation.metrics` -- these operate on plain ranked recipe-id lists
against a ground-truth relevant-id set, so they apply equally to the
semantic (Chroma) and keyword retrieval paths.
"""

from __future__ import annotations

import math


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of the relevant set that appears in the top-k results."""
    if not relevant_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    """1 / rank of the first relevant result (0.0 if none found)."""
    for position, recipe_id in enumerate(ranked_ids, start=1):
        if recipe_id in relevant_ids:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Binary-relevance nDCG@k (relevant=1, irrelevant=0)."""
    if not relevant_ids:
        return 0.0
    dcg = 0.0
    for position, recipe_id in enumerate(ranked_ids[:k], start=1):
        if recipe_id in relevant_ids:
            dcg += 1.0 / math.log2(position + 1)
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_hits + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg
