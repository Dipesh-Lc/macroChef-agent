import math

from app.schemas.recommendation import RecipeScore
from app.schemas.recipe import Recipe


def rank_recipes(
    recipes: list[Recipe],
    scores: dict[str, RecipeScore],
    limit: int = 3,
    pantry_bucket: float = 0.1,
) -> list[tuple[Recipe, RecipeScore]]:
    """Rank recipes with pantry match as the primary sort key.

    Recipes are grouped into `pantry_bucket`-wide bands of
    `RecipeScore.pantry_match_score` (default 10% bands), and sorted
    primarily by descending bucket. Within the same bucket, `final_score`
    (the blended pantry/macro/cook-time/preference score from
    `nutrition_scorer.score_recipe`) breaks ties. This guarantees a recipe
    with a meaningfully higher pantry match always outranks one with a
    lower pantry match, regardless of macro/time/preference fit -- pantry
    match is the unambiguous top priority, not just the heaviest of several
    blended weights.
    """

    def sort_key(item: tuple[Recipe, RecipeScore]) -> tuple[float, float]:
        _, score = item
        bucket = math.floor(score.pantry_match_score / pantry_bucket) if pantry_bucket > 0 else 0
        return (bucket, score.final_score)

    ranked = sorted(
        ((recipe, scores[recipe.recipe_id]) for recipe in recipes if recipe.recipe_id in scores),
        key=sort_key,
        reverse=True,
    )
    return ranked[:limit]
