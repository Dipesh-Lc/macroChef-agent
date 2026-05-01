import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.recipe_indexing_service import RecipeIndexingService  # noqa: E402


def main() -> None:
    count = RecipeIndexingService().rebuild_index(include_base=True, include_user=True)
    print(f"Indexed {count} base and user-saved recipes.")


if __name__ == "__main__":
    main()
