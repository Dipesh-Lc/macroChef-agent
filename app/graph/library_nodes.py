from app.data.recipe_library_repository import RecipeLibraryRepository
from app.graph.library_state import (
    RecipeLibraryBuilderState,
    ensure_library_state,
    library_state_update,
)
from app.rag.loaders import load_recipes
from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.recipe_dedup_service import RecipeDedupService
from app.services.recipe_discovery_service import RecipeDiscoveryService
from app.services.recipe_indexing_service import RecipeIndexingService
from app.services.recipe_validation_service import RecipeValidationService


def _trace(state: RecipeLibraryBuilderState, message: str) -> list[str]:
    return [*state.debug_trace, message]


def _request_from_state(state: RecipeLibraryBuilderState) -> RecipeDiscoveryRequest:
    return RecipeDiscoveryRequest(
        user_id=state.user_id,
        cuisines=state.cuisines,
        meal_type=state.meal_type,
        diet_type=state.diet_type,
        max_cook_time_min=state.max_cook_time_min,
        difficulty=state.difficulty,
        count=state.count,
        home_cookable=state.home_cookable,
        excluded_ingredients=state.excluded_ingredients,
        allergies=state.allergies,
        extra_preferences=state.extra_preferences,
        source_mode=state.source_mode,  # type: ignore[arg-type]
    )


def discovery_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    request = _request_from_state(current)
    service = RecipeDiscoveryService()
    try:
        candidates = service.discover(request)
    except Exception as exc:
        return library_state_update(
            current,
            errors=[f"Recipe discovery failed: {exc}"],
            warnings=[*current.warnings, f"Recipe discovery failed: {exc}"],
            debug_trace=_trace(current, f"discovery_node: failed: {exc}"),
        )
    return library_state_update(
        current,
        raw_candidates=[candidate.model_dump() for candidate in candidates],
        warnings=[*current.warnings, *service.warnings],
        debug_trace=_trace(
            current,
            f"discovery_node: discovered {len(candidates)} raw candidates.",
        ),
    )


def normalization_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    normalized: list[RecipeCandidate] = []
    for raw in current.raw_candidates:
        candidate = RecipeCandidate.model_validate(raw)
        candidate = candidate.model_copy(
            update={
                "title": " ".join(candidate.title.split()).title(),
                "cuisine": candidate.cuisine.title() if candidate.cuisine else None,
                "meal_type": candidate.meal_type.lower() if candidate.meal_type else None,
                "difficulty": candidate.difficulty.lower() if candidate.difficulty else None,
                "ingredients": [
                    " ".join(item.split())
                    for item in candidate.ingredients
                    if item.strip()
                ],
                "diet_tags": sorted({tag.strip().lower() for tag in candidate.diet_tags if tag}),
                "allergens": sorted({tag.strip().lower() for tag in candidate.allergens if tag}),
            }
        )
        normalized.append(candidate)
    return library_state_update(
        current,
        normalized_candidates=normalized,
        debug_trace=_trace(
            current,
            f"normalization_node: normalized {len(normalized)} candidates.",
        ),
    )


def recipe_validation_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    result = RecipeValidationService().validate_candidates(
        current.normalized_candidates,
        _request_from_state(current),
    )
    return library_state_update(
        current,
        validated_candidates=result.valid_candidates,
        failed_candidates=[*current.failed_candidates, *result.failed_candidates],
        warnings=[*current.warnings, *result.warnings],
        debug_trace=_trace(
            current,
            f"recipe_validation_node: {len(result.valid_candidates)} valid candidates.",
        ),
    )


def deduplication_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    existing = [
        *load_recipes(),
        *RecipeLibraryRepository().list_user_recipes(current.user_id),
    ]
    result = RecipeDedupService().deduplicate(current.validated_candidates, existing)
    duplicate_titles = [candidate.title for candidate in result.duplicate_candidates]
    return library_state_update(
        current,
        validated_candidates=result.unique_candidates,
        duplicate_candidates=result.duplicate_candidates,
        skipped_duplicates=duplicate_titles,
        warnings=[
            *current.warnings,
            *[
                f"Duplicate skipped: {candidate.title}"
                for candidate in result.duplicate_candidates
            ],
        ],
        debug_trace=_trace(
            current,
            (
                "deduplication_node: kept "
                f"{len(result.unique_candidates)} unique, "
                f"skipped {len(result.duplicate_candidates)}."
            ),
        ),
    )


def candidate_presentation_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    return library_state_update(
        current,
        debug_trace=_trace(
            current,
            (
                "candidate_presentation_node: returned "
                f"{len(current.validated_candidates)} candidates."
            ),
        ),
    )


def selected_candidate_validation_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    result = RecipeValidationService().validate_candidates(current.selected_candidates)
    if result.failed_candidates:
        return library_state_update(
            current,
            failed_candidates=[*current.failed_candidates, *result.failed_candidates],
            selected_candidates=result.valid_candidates,
            warnings=[*current.warnings, *result.warnings],
            debug_trace=_trace(
                current,
                (
                    "selected_candidate_validation_node: "
                    f"{len(result.valid_candidates)} valid, {len(result.failed_candidates)} failed."
                ),
            ),
        )
    return library_state_update(
        current,
        selected_candidates=result.valid_candidates,
        warnings=[*current.warnings, *result.warnings],
        debug_trace=_trace(
            current,
            (
                "selected_candidate_validation_node: validated "
                f"{len(result.valid_candidates)} selected."
            ),
        ),
    )


def save_recipe_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    repository = RecipeLibraryRepository()
    existing = [
        *load_recipes(),
        *repository.list_user_recipes(current.user_id),
    ]
    deduped = RecipeDedupService().deduplicate(current.selected_candidates, existing)
    saved = []
    saved_ids = []
    for candidate in deduped.unique_candidates:
        recipe = candidate.to_recipe(current.user_id)
        recipe_id = repository.save_recipe(current.user_id, recipe)
        saved.append(recipe)
        saved_ids.append(recipe_id)
    return library_state_update(
        current,
        saved_recipes=saved,
        saved_recipe_ids=saved_ids,
        skipped_duplicates=[candidate.title for candidate in deduped.duplicate_candidates],
        debug_trace=_trace(
            current,
            f"save_recipe_node: saved {len(saved_ids)} recipes.",
        ),
    )


def index_recipe_node(state: RecipeLibraryBuilderState | dict):
    current = ensure_library_state(state)
    indexed_count = RecipeIndexingService().index_recipes(current.saved_recipes)
    return library_state_update(
        current,
        indexed_count=indexed_count,
        debug_trace=_trace(
            current,
            f"index_recipe_node: indexed {indexed_count} recipes.",
        ),
    )
