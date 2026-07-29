import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.recipe_indexing_service import RecipeIndexingService  # noqa: E402


def main() -> None:
    # Clean rebuild of the FULL grounded corpus (base + user-saved), not the
    # seeds-only/upsert path app.rag.build_index.build_recipe_index used to
    # take (see that module's docstring). rebuild_index_clean drops and
    # recreates the vector store's index first, so a re-run never leaves
    # stale ids/metadata behind from a smaller or corrected corpus. Backend
    # (Chroma default, or pgvector) is whatever VECTOR_BACKEND resolves to
    # -- see app.rag.vector_store; scripts/seed_pgvector.py exists as an
    # explicit pgvector-only entrypoint for the release seeding job.
    count = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=True)
    backend = get_settings().vector_backend
    print(f"Indexed {count} recipes into the {backend} vector store.")


if __name__ == "__main__":
    main()
