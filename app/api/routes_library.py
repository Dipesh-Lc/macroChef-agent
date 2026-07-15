from fastapi import APIRouter, HTTPException

from app.data.recipe_library_repository import RecipeLibraryRepository
from app.graph.library_builder import run_library_discovery_graph, run_library_save_graph
from app.schemas.library import (
    DeleteRecipeResponse,
    RecipeDiscoveryRequest,
    RecipeDiscoveryResponse,
    ReindexLibraryResponse,
    SaveRecipeCandidatesRequest,
    SaveRecipeCandidatesResponse,
    UserRecipeLibraryResponse,
)
from app.services.recipe_indexing_service import RecipeIndexingService

router = APIRouter(prefix="/library", tags=["recipe-library"])


@router.post("/discover", response_model=RecipeDiscoveryResponse)
def discover_recipes(request: RecipeDiscoveryRequest) -> RecipeDiscoveryResponse:
    return run_library_discovery_graph(request)


@router.post("/save", response_model=SaveRecipeCandidatesResponse)
def save_recipe_candidates(request: SaveRecipeCandidatesRequest) -> SaveRecipeCandidatesResponse:
    return run_library_save_graph(request)


@router.post("/reindex", response_model=ReindexLibraryResponse)
def reindex_recipe_library() -> ReindexLibraryResponse:
    # Intentionally `rebuild_index` (upsert), not `rebuild_index_clean`: this
    # is a synchronous request-latency-sensitive endpoint, and
    # `rebuild_index_clean` drops and re-embeds the ENTIRE collection
    # (base corpus + all user recipes -- thousands of documents) on every
    # call, which would make a single reindex request far too slow. Upsert
    # never prunes stale/orphaned ids left behind by a smaller or corrected
    # corpus re-import (see app/services/recipe_indexing_service.py), so
    # periodic clean rebuilds still belong in the offline
    # scripts/backfill_recipe_library.py / scripts/ingest_recipes.py path,
    # not this endpoint. This same staleness is the source of the `user_*`
    # ids the retrieval eval had to filter out of raw Chroma results -- see
    # app.evaluation.eval_retrieval.semantic_search_ids.
    indexed_count = RecipeIndexingService().rebuild_index(include_base=True, include_user=True)
    return ReindexLibraryResponse(indexed_count=indexed_count, status="ok")


@router.get("/{user_id}", response_model=UserRecipeLibraryResponse)
def list_user_recipe_library(user_id: str) -> UserRecipeLibraryResponse:
    recipes = RecipeLibraryRepository().list_user_recipes(user_id)
    return UserRecipeLibraryResponse(recipes=recipes)


@router.delete("/{user_id}/{recipe_id}", response_model=DeleteRecipeResponse)
def delete_user_recipe(user_id: str, recipe_id: str) -> DeleteRecipeResponse:
    deleted = RecipeLibraryRepository().deactivate_recipe(user_id, recipe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved recipe not found")
    return DeleteRecipeResponse(recipe_id=recipe_id, deleted=True)
