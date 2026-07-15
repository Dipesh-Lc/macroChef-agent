from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.recipe_indexing_service import RecipeIndexingService  # noqa: E402


def main() -> None:
    # Clean rebuild of the FULL grounded corpus (base + user-saved), not the
    # seeds-only/upsert path app.rag.build_index.build_recipe_index used to
    # take (see that module's docstring). rebuild_index_clean drops and
    # recreates the Chroma collection first, so a re-run never leaves stale
    # ids/metadata behind from a smaller or corrected corpus.
    count = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=True)
    print(f"Indexed {count} recipes into Chroma.")


if __name__ == "__main__":
    main()
