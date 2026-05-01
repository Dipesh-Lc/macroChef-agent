from app.data.recipe_library_repository import RecipeLibraryRepository
from app.rag.chroma_client import get_chroma_collection
from app.rag.loaders import load_recipes
from app.schemas.recipe import Recipe
from app.services.constraint_engine import ALLERGEN_ALIASES
from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)


INDEX_ALLERGENS = [
    "dairy",
    "peanut",
    "tree nut",
    "egg",
    "soy",
    "gluten",
    "shellfish",
    "fish",
]


def build_recipe_search_document(recipe: Recipe) -> str:
    macros = (
        f"calories {recipe.calories}, protein {recipe.protein_g}g, carbs {recipe.carbs_g}g, "
        f"fat {recipe.fat_g}g, fiber {recipe.fiber_g}g"
    )
    notes = "User-saved home-cookable recipe." if recipe.is_user_saved else "Base sample recipe."
    return "\n".join(
        [
            f"Title: {recipe.title}",
            f"Cuisine: {recipe.cuisine or 'unknown'}",
            f"Meal type: {recipe.meal_type or 'any'}",
            f"Description: {recipe.description or ''}",
            f"Ingredients: {', '.join(recipe.ingredients)}",
            f"Diet tags: {', '.join(recipe.diet_tags)}",
            f"Cook time: {recipe.cook_time_min or 'unknown'} minutes",
            f"Difficulty: {recipe.difficulty or 'unknown'}",
            f"Macros: {macros}.",
            f"Home-cookable notes: {notes}",
        ]
    )


def recipe_index_metadata(recipe: Recipe) -> dict[str, str | int | float | bool | None]:
    metadata: dict[str, str | int | float | bool | None] = {
        "recipe_id": recipe.recipe_id,
        "title": recipe.title,
        "cuisine": recipe.cuisine,
        "meal_type": recipe.meal_type,
        "cook_time_min": recipe.cook_time_min,
        "calories": recipe.calories,
        "protein_g": recipe.protein_g,
        "carbs_g": recipe.carbs_g,
        "fat_g": recipe.fat_g,
        "fiber_g": recipe.fiber_g,
        "owner_user_id": recipe.owner_user_id,
        "is_user_saved": recipe.is_user_saved,
        "is_active": recipe.is_active,
        "source_type": recipe.source_type,
    }
    terms = _recipe_allergen_terms(recipe)
    for allergen in INDEX_ALLERGENS:
        metadata[f"contains_{allergen.replace(' ', '_')}"] = allergen in terms
    return {key: value for key, value in metadata.items() if value is not None}


class RecipeIndexingService:
    def __init__(self, repository: RecipeLibraryRepository | None = None):
        self.repository = repository or RecipeLibraryRepository()

    def index_recipe(self, recipe: Recipe) -> None:
        self.index_recipes([recipe])

    def index_recipes(self, recipes: list[Recipe]) -> int:
        if not recipes:
            return 0
        try:
            collection = get_chroma_collection()
            collection.upsert(
                ids=[recipe.recipe_id for recipe in recipes],
                documents=[build_recipe_search_document(recipe) for recipe in recipes],
                metadatas=[recipe_index_metadata(recipe) for recipe in recipes],
            )
            return len(recipes)
        except Exception as exc:
            logger.warning(
                "Could not index recipes in Chroma; keyword fallback remains available: %s",
                exc,
            )
            return 0

    def rebuild_index(self, include_base: bool = True, include_user: bool = True) -> int:
        recipes: list[Recipe] = []
        if include_base:
            recipes.extend(load_recipes())
        if include_user:
            recipes.extend(self.repository.list_all_active_user_recipes())
        return self.index_recipes(recipes)


def _recipe_allergen_terms(recipe: Recipe) -> set[str]:
    terms = {
        normalize_ingredient(item).lower()
        for item in [*recipe.ingredients, *recipe.allergens]
        if item
    }
    expanded = set(terms)
    for allergen, aliases in ALLERGEN_ALIASES.items():
        alias_terms = {normalize_ingredient(item).lower() for item in aliases}
        if allergen in terms or terms.intersection(alias_terms):
            expanded.add(allergen)
    return expanded
