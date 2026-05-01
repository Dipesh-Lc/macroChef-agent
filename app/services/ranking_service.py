from app.schemas.recommendation import RecipeScore
from app.schemas.recipe import Recipe


def rank_recipes(
    recipes: list[Recipe], scores: dict[str, RecipeScore], limit: int = 3
) -> list[tuple[Recipe, RecipeScore]]:
    ranked = sorted(
        ((recipe, scores[recipe.recipe_id]) for recipe in recipes if recipe.recipe_id in scores),
        key=lambda item: item[1].final_score,
        reverse=True,
    )
    return ranked[:limit]
