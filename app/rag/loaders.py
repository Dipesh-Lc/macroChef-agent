import json
from pathlib import Path

from app.config import get_settings
from app.schemas.recipe import Recipe


def load_recipes(path: str | Path | None = None) -> list[Recipe]:
    settings = get_settings()
    recipe_path = Path(path) if path else settings.recipe_path
    if not recipe_path.exists():
        return []

    recipes: list[Recipe] = []
    with recipe_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                recipes.append(Recipe.model_validate(json.loads(line)))
    return recipes


def recipes_by_id(path: str | Path | None = None) -> dict[str, Recipe]:
    return {recipe.recipe_id: recipe for recipe in load_recipes(path)}


def load_corpus(
    seed_path: str | Path | None = None,
    imported_path: str | Path | None = None,
) -> list[Recipe]:
    """Union of the hand-curated seed recipes and the imported corpus.

    The 25 seed recipes (`sample_recipes.jsonl`) are never rewritten by the
    import pipeline; imported recipes live in a separate file
    (`imported_recipes.jsonl`) that is fully rewritten on each import run. This
    loads both and dedupes by `recipe_id`, with seeds taking precedence so a
    colliding imported id can never shadow a curated recipe.
    """
    settings = get_settings()
    seeds = load_recipes(seed_path if seed_path is not None else settings.recipe_path)
    imported_default = Path(settings.recipe_path).parent / "imported_recipes.jsonl"
    imported = load_recipes(imported_path if imported_path is not None else imported_default)

    by_id: dict[str, Recipe] = {}
    for recipe in imported:
        by_id[recipe.recipe_id] = recipe
    for recipe in seeds:
        by_id[recipe.recipe_id] = recipe
    return list(by_id.values())
