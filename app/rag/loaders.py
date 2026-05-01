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
