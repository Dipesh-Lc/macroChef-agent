"""Corpus-wide diet-leak regression gate.

Treated as a release blocker the same way the allergy-violation rate is: this
must show 0 leaking recipes for vegan/vegetarian/gluten-free/dairy-free across
the full imported corpus, or the corpus isn't safe to serve for those diets.
See scripts/audit_diet_leaks.py for the standalone, human-readable report
(sample leaking titles, leak rate) and for why the ground-truth term lists
here are independent of constraint_engine's own tables.
"""

import pytest

from scripts.audit_diet_leaks import DEFAULT_CORPUS_PATH, _load_corpus, audit

_CORPUS = _load_corpus(DEFAULT_CORPUS_PATH) if DEFAULT_CORPUS_PATH.exists() else []


@pytest.mark.skipif(not _CORPUS, reason="imported_recipes.jsonl corpus not present")
@pytest.mark.parametrize("diet_type", ["vegan", "vegetarian", "gluten-free", "dairy-free"])
def test_no_diet_leaks_across_full_corpus(diet_type: str) -> None:
    result = audit(_CORPUS, diet_type)

    # Non-vacuous gate: a future change that over-rejects everything (0 recipes
    # pass the filter) would trivially show 0 leaks without actually proving
    # anything. Require the filter to actually admit recipes for this diet.
    assert result["passed_filter"] > 0, (
        f"{diet_type}: 0/{result['corpus_size']} recipes passed the filter -- "
        f"the leak assertion below would be vacuously true, which is not a "
        f"meaningful safety gate."
    )

    assert result["leaking"] == 0, (
        f"{diet_type}: {result['leaking']}/{result['passed_filter']} recipes marked "
        f"safe still contain an excluded ingredient, e.g. {result['sample_leaks']}"
    )
