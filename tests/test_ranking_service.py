from app.schemas.recipe import Recipe
from app.schemas.recommendation import RecipeScore
from app.services.ranking_service import rank_recipes


def _recipe(recipe_id: str) -> Recipe:
    return Recipe(recipe_id=recipe_id, title=recipe_id)


def _score(
    recipe_id: str,
    pantry_match_score: float,
    final_score: float,
    macro_fit_score: float = 0.5,
) -> RecipeScore:
    return RecipeScore(
        recipe_id=recipe_id,
        pantry_match_score=pantry_match_score,
        macro_fit_score=macro_fit_score,
        time_score=0.5,
        preference_score=0.5,
        final_score=final_score,
    )


def test_high_pantry_match_outranks_low_pantry_match_despite_worse_final_score() -> None:
    # "high_pantry" has a much higher pantry match than "high_macro", even
    # though "high_macro" wins on the blended final_score (e.g. from a
    # perfect macro fit). Pantry match must still win.
    high_pantry = _recipe("high_pantry")
    high_macro = _recipe("high_macro")
    scores = {
        "high_pantry": _score("high_pantry", pantry_match_score=0.95, final_score=0.55),
        "high_macro": _score("high_macro", pantry_match_score=0.20, final_score=0.90),
    }

    ranked = rank_recipes([high_pantry, high_macro], scores, limit=2)

    assert [recipe.recipe_id for recipe, _ in ranked] == ["high_pantry", "high_macro"]


def test_same_pantry_bucket_breaks_tie_on_final_score() -> None:
    # Both recipes fall in the same 10%-wide pantry bucket (0.81 and 0.86
    # both floor to bucket 8), so final_score should decide the order.
    recipe_a = _recipe("recipe_a")
    recipe_b = _recipe("recipe_b")
    scores = {
        "recipe_a": _score("recipe_a", pantry_match_score=0.81, final_score=0.40),
        "recipe_b": _score("recipe_b", pantry_match_score=0.86, final_score=0.75),
    }

    ranked = rank_recipes([recipe_a, recipe_b], scores, limit=2)

    assert [recipe.recipe_id for recipe, _ in ranked] == ["recipe_b", "recipe_a"]


def test_limit_truncates_ranked_results() -> None:
    recipes = [_recipe(f"r{i}") for i in range(5)]
    scores = {
        f"r{i}": _score(f"r{i}", pantry_match_score=0.1 * i, final_score=0.1 * i)
        for i in range(5)
    }

    ranked = rank_recipes(recipes, scores, limit=2)

    assert len(ranked) == 2
    assert [recipe.recipe_id for recipe, _ in ranked] == ["r4", "r3"]


def test_recipes_without_scores_are_excluded() -> None:
    scored = _recipe("scored")
    unscored = _recipe("unscored")
    scores = {"scored": _score("scored", pantry_match_score=0.5, final_score=0.5)}

    ranked = rank_recipes([scored, unscored], scores, limit=5)

    assert [recipe.recipe_id for recipe, _ in ranked] == ["scored"]
