from app.schemas.recipe import Recipe
from app.services.recipe_indexing_service import build_recipe_search_document, recipe_index_metadata


def recipe_to_document(recipe: Recipe) -> str:
    return build_recipe_search_document(recipe)


def recipe_to_metadata(recipe: Recipe) -> dict[str, str | int | float | bool | None]:
    return recipe_index_metadata(recipe)
