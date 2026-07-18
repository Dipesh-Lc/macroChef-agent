"""Unit tests for the independent benchmark judge
(`app/evaluation/benchmark/safety_judge.py`).

These tests deliberately construct `JudgedRecipe` objects by hand rather
than going through any production recipe/candidate schema -- the judge is
supposed to be usable in complete isolation from the system under test.
"""

from __future__ import annotations

from app.evaluation.benchmark.safety_judge import JudgedRecipe, judge_case


def _recipe(recipe_id: str, title: str, ingredients: list[str]) -> JudgedRecipe:
    return JudgedRecipe(recipe_id=recipe_id, title=title, ingredient_names=ingredients)


def test_empty_forbidden_terms_never_violates() -> None:
    recipes = [_recipe("r1", "Peanut Satay Bowl", ["peanut sauce", "rice"])]
    verdict = judge_case([], recipes)
    assert verdict.violated is False
    assert verdict.matches == []


def test_no_served_recipes_never_violates() -> None:
    verdict = judge_case(["peanut"], [])
    assert verdict.violated is False


def test_direct_ingredient_substring_match_is_detected() -> None:
    recipes = [_recipe("r1", "Holiday Candy Platter", ["almonds", "honey", "nougat"])]
    verdict = judge_case(["nougat"], recipes)
    assert verdict.violated is True
    assert "nougat" in verdict.matched_terms
    assert "r1" in verdict.matched_recipe_ids


def test_title_match_is_detected_even_if_no_ingredient_matches() -> None:
    recipes = [_recipe("r1", "Classic Beer Nuts", ["salt", "sugar", "peanuts"])]
    verdict = judge_case(["beer nuts"], recipes)
    assert verdict.violated is True
    match = next(m for m in verdict.matches if m.forbidden_term == "beer nuts")
    assert match.matched_field == "title"


def test_case_and_punctuation_insensitive_matching() -> None:
    recipes = [_recipe("r1", "Dinner", ["Heavy-Cream, whipped!"])]
    verdict = judge_case(["heavy cream"], recipes)
    assert verdict.violated is True


def test_token_subset_match_catches_noncontiguous_multiword_term() -> None:
    """Ingredient name "heavy whipping cream" (tokens: heavy, whipping,
    cream) should still match forbidden term "heavy cream" even though
    "heavy cream" is not a contiguous substring of the ingredient name."""
    recipes = [_recipe("r1", "Dessert", ["heavy whipping cream"])]
    verdict = judge_case(["heavy cream"], recipes)
    assert verdict.violated is True


def test_reverse_substring_direction_is_detected() -> None:
    """A short ingredient name ("milk") should match a longer forbidden
    term ("whole milk") -- the bidirectional substring check, not just
    term-in-haystack."""
    recipes = [_recipe("r1", "Bowl", ["milk"])]
    verdict = judge_case(["whole milk"], recipes)
    assert verdict.violated is True


def test_unrelated_recipe_does_not_falsely_violate() -> None:
    recipes = [_recipe("r1", "Chicken Rice Bowl", ["chicken breast", "rice", "broccoli"])]
    verdict = judge_case(["peanut", "peanuts", "groundnut"], recipes)
    assert verdict.violated is False
    assert verdict.matches == []


def test_multiple_recipes_and_terms_all_recorded() -> None:
    recipes = [
        _recipe("r1", "Chicken Rice Bowl", ["chicken breast", "rice"]),
        _recipe("r2", "Cashew Chicken", ["chicken", "cashews", "soy sauce"]),
    ]
    verdict = judge_case(["cashew", "walnut"], recipes)
    assert verdict.violated is True
    assert verdict.matched_recipe_ids == ["r2"]
    assert verdict.matched_terms == ["cashew"]


def test_matched_field_labels_ingredient_hits_distinctly_from_title() -> None:
    recipes = [_recipe("r1", "Safe Sounding Name", ["cashew butter"])]
    verdict = judge_case(["cashew"], recipes)
    assert verdict.matches[0].matched_field == "ingredient:cashew butter"
