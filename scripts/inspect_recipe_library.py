import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.recipe_library_repository import RecipeLibraryRepository  # noqa: E402


def main() -> None:
    recipes = RecipeLibraryRepository().list_all_active_user_recipes()
    if not recipes:
        print("No active user-saved recipes found.")
        return
    for recipe in recipes:
        print(
            f"{recipe.owner_user_id}: {recipe.recipe_id} | {recipe.title} | "
            f"{recipe.cuisine or 'Any'} | {recipe.meal_type or 'meal'}"
        )


if __name__ == "__main__":
    main()
