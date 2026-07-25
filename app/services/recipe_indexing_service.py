from app.data.recipe_library_repository import RecipeLibraryRepository
from app.rag.chroma_client import get_chroma_collection, reset_chroma_collection
from app.rag.loaders import load_corpus
from app.schemas.recipe import Recipe
from app.services.constraint_engine import derive_allergen_labels
from app.services.nutrition_view import macro_display_state, trusted_per_serving
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


def _macro_index_text(recipe: Recipe) -> str:
    """Macro text for the search document, gated by the same
    `macro_display_state` the scorer/frontend/explanation layer use (see
    app.services.nutrition_view) -- never the recipe's self-reported tag
    fields (recipe.calories/protein_g/...), which are unverified until
    GROUNDED. Where macros are unknown or only partially grounded, the
    document says so in plain text rather than embedding a fabricated or
    undercounted number as if it were reliable."""
    state = macro_display_state(recipe)
    if state == "unknown":
        return "Macros have not been verified for this recipe yet."

    macros = trusted_per_serving(recipe) or recipe.nutrition.per_serving
    text = (
        f"calories {macros.calories:.0f}, protein {macros.protein_g:.0f}g, "
        f"carbs {macros.carbs_g:.0f}g, fat {macros.fat_g:.0f}g, fiber {macros.fiber_g:.0f}g"
    )
    if state == "partial":
        coverage_pct = round(recipe.nutrition.coverage * 100)
        return f"{text} (partial -- based on {coverage_pct}% of ingredients, likely an undercount)"
    return text


def build_recipe_search_document(recipe: Recipe) -> str:
    notes = "User-saved home-cookable recipe." if recipe.is_user_saved else "Base sample recipe."
    return "\n".join(
        [
            f"Title: {recipe.title}",
            f"Cuisine: {recipe.cuisine or 'unknown'}",
            f"Meal type: {recipe.meal_type or 'any'}",
            f"Description: {recipe.description or ''}",
            f"Ingredients: {', '.join(item.name for item in recipe.ingredients)}",
            f"Diet tags: {', '.join(recipe.diet_tags)}",
            f"Cook time: {recipe.cook_time_min or 'unknown'} minutes",
            f"Difficulty: {recipe.difficulty or 'unknown'}",
            f"Macros: {_macro_index_text(recipe)}.",
            f"Home-cookable notes: {notes}",
        ]
    )


def recipe_index_metadata(recipe: Recipe) -> dict[str, str | int | float | bool | None]:
    # Only fully GROUNDED per-serving macros are indexed as numeric metadata --
    # PARTIAL systematically undercounts (see app.services.nutrition_view), so
    # it's excluded here the same way the scorer excludes it from macro_fit_score.
    macros = trusted_per_serving(recipe)
    metadata: dict[str, str | int | float | bool | None] = {
        "recipe_id": recipe.recipe_id,
        "title": recipe.title,
        "cuisine": recipe.cuisine,
        "meal_type": recipe.meal_type,
        "cook_time_min": recipe.cook_time_min,
        "calories": macros.calories if macros else None,
        "protein_g": macros.protein_g if macros else None,
        "carbs_g": macros.carbs_g if macros else None,
        "fat_g": macros.fat_g if macros else None,
        "fiber_g": macros.fiber_g if macros else None,
        "owner_user_id": recipe.owner_user_id,
        "is_user_saved": recipe.is_user_saved,
        "is_active": recipe.is_active,
        "source_type": recipe.source_type,
    }
    terms = _recipe_allergen_terms(recipe)
    for allergen in INDEX_ALLERGENS:
        metadata[f"contains_{allergen.replace(' ', '_')}"] = allergen in terms
    return {key: value for key, value in metadata.items() if value is not None}


DEFAULT_MAX_BATCH_SIZE = 5461
"""Fallback only -- used when the collection can't report its own limit
(e.g. a lightweight test fake with no `_client`). The real limit is always
queried at runtime via `_resolve_max_batch_size` so this stays correct if
chromadb's own ceiling ever changes."""


def _resolve_max_batch_size(collection, default: int = DEFAULT_MAX_BATCH_SIZE) -> int:
    """Ask the underlying Chroma client for its actual max batch size.

    `collection.upsert(...)` raises `ValueError` if given more items than
    the client's `get_max_batch_size()` in one call (observed at 5,461 on
    the installed chromadb version). Querying it at runtime -- rather than
    hardcoding a constant -- means this stays correct if that limit ever
    changes in a future chromadb release.
    """
    client = getattr(collection, "_client", None)
    get_max_batch_size = getattr(client, "get_max_batch_size", None)
    if callable(get_max_batch_size):
        try:
            resolved = int(get_max_batch_size())
            if resolved > 0:
                return resolved
        except Exception:
            pass
    return default


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
            max_batch_size = _resolve_max_batch_size(collection)

            ids = [recipe.recipe_id for recipe in recipes]
            documents = [build_recipe_search_document(recipe) for recipe in recipes]
            metadatas = [recipe_index_metadata(recipe) for recipe in recipes]

            indexed = 0
            for start in range(0, len(recipes), max_batch_size):
                end = start + max_batch_size
                collection.upsert(
                    ids=ids[start:end],
                    documents=documents[start:end],
                    metadatas=metadatas[start:end],
                )
                indexed += len(ids[start:end])
            return indexed
        except Exception as exc:
            logger.warning(
                "Could not index recipes in Chroma; keyword fallback remains available: %s",
                exc,
            )
            return 0

    def rebuild_index(self, include_base: bool = True, include_user: bool = True) -> int:
        return self.index_recipes(self._collect_recipes(include_base, include_user))

    def rebuild_index_clean(self, include_base: bool = True, include_user: bool = True) -> int:
        """Drop-and-recreate the Chroma collection, then index from scratch.

        `index_recipes` uses `upsert`, which never prunes ids that are no
        longer present in the source (e.g. a corpus re-import with a smaller
        or corrected dataset). This variant guarantees no orphaned embeddings
        survive a re-run.
        """
        recipes = self._collect_recipes(include_base, include_user)
        reset_chroma_collection()
        return self.index_recipes(recipes)

    def _collect_recipes(self, include_base: bool, include_user: bool) -> list[Recipe]:
        recipes: list[Recipe] = []
        if include_base:
            recipes.extend(load_corpus())
        if include_user:
            recipes.extend(self.repository.list_all_active_user_recipes())
        return recipes


def _recipe_allergen_terms(recipe: Recipe) -> set[str]:
    names = [*(ingredient.name for ingredient in recipe.ingredients), *recipe.allergens]
    return set(derive_allergen_labels(names))
