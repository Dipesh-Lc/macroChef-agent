from app.config import get_settings
from app.rag.loaders import load_recipes
from app.services.recipe_indexing_service import RecipeIndexingService


def build_recipe_index(include_user_recipes: bool = False) -> int:
    settings = get_settings()
    recipes = load_recipes(settings.recipe_path)
    service = RecipeIndexingService()
    if include_user_recipes:
        return service.rebuild_index(include_base=True, include_user=True)
    service.index_recipes(recipes)
    return len(recipes)
