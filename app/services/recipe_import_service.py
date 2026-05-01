from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate


class RecipeImportService:
    """MVP placeholder for approved external/curated recipe import sources."""

    def import_candidates(self, request: RecipeDiscoveryRequest) -> list[RecipeCandidate]:
        # Intentionally does not scrape arbitrary websites. Future versions can connect
        # to licensed datasets or user-uploaded recipe files through this boundary.
        return []
