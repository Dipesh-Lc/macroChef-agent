"""Corpus-wide diet-leak regression gate.

Treated as a release blocker the same way the allergy-violation rate is: this
must show 0 leaking recipes for vegan/vegetarian/gluten-free/dairy-free across
the full imported corpus, or the corpus isn't safe to serve for those diets.
See scripts/audit_diet_leaks.py for the standalone, human-readable report
(sample leaking titles, leak rate) and for why the ground-truth term lists
here are independent of constraint_engine's own tables.
"""

import pytest

from app.schemas.recipe import Recipe
from scripts.audit_diet_leaks import DEFAULT_CORPUS_PATH, DIET_GROUND_TRUTH, _ground_truth_violates, _load_corpus, audit

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


# --- Audit-side false-positive carve-out (A1 revise round, 2026-07-19) -----
# GROUND_TRUTH_FALSE_POSITIVE_PAIRS's "curd" -> "bean curd" entry, the
# audit-side twin of constraint_engine._LOOKALIKE_EXCLUSIONS["curd"].


def _recipe(ingredients: list[str]) -> Recipe:
    return Recipe(recipe_id="r", title="t", ingredients=ingredients, instructions=["Cook.", "Serve."])


def test_ground_truth_does_not_flag_bean_curd_for_dairy() -> None:
    recipe = _recipe(["bean curd", "rice"])
    assert _ground_truth_violates(recipe, DIET_GROUND_TRUTH["dairy-free"]) is False


def test_ground_truth_still_flags_cheese_curds_for_dairy() -> None:
    recipe = _recipe(["cheese curds", "rice"])
    assert _ground_truth_violates(recipe, DIET_GROUND_TRUTH["dairy-free"]) is True


def test_ground_truth_flags_real_dairy_curd_alongside_bean_curd() -> None:
    # Per-pair semantics: bean curd's own match is suppressed, but a SEPARATE
    # real dairy ingredient in the same recipe is not hidden by it.
    recipe = _recipe(["bean curd", "cheese curds", "rice"])
    assert _ground_truth_violates(recipe, DIET_GROUND_TRUTH["dairy-free"]) is True
