from app.config import get_settings
from app.rag.loaders import load_recipes
from app.services.recipe_indexing_service import RecipeIndexingService


def build_recipe_index(include_user_recipes: bool = False) -> int:
    """DEPRECATED: no longer called anywhere in this repo.

    The default branch here (`include_user_recipes=False`) only loads
    `settings.recipe_path` -- the 25 curated seeds, not the full imported
    corpus -- and indexes via `index_recipes` (upsert), which never prunes
    stale ids/metadata from a smaller or corrected re-import. That combination
    is exactly the "seeds-only/ungrounded via upsert" reindex path the repo
    disallows for a default entrypoint. Use
    `RecipeIndexingService().rebuild_index_clean(include_base=True,
    include_user=True)` instead (see scripts/ingest_recipes.py,
    scripts/backfill_recipe_library.py, scripts/import_corpus.py), which
    indexes the full corpus via a clean drop-and-recreate. Kept only for
    backward compatibility with any external callers; not exercised by any
    repo script.
    """
    settings = get_settings()
    recipes = load_recipes(settings.recipe_path)
    service = RecipeIndexingService()
    if include_user_recipes:
        return service.rebuild_index(include_base=True, include_user=True)
    service.index_recipes(recipes)
    return len(recipes)
