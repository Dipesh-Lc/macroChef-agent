import json
from pathlib import Path

from app.config import get_settings
from app.schemas.nutrition import RecipeNutrition
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


def load_grounding(path: str | Path | None = None) -> dict[str, RecipeNutrition]:
    """Load the grounding sidecar (app.services.grounding_job) keyed by recipe_id.

    Returns {} if the job has never run -- callers then leave every recipe's
    `nutrition` at its default None, which reads as "unknown" everywhere
    (see app.services.nutrition_view) rather than erroring.
    """
    settings = get_settings()
    grounding_path = Path(path) if path else Path(settings.recipe_path).parent / "grounding.jsonl"
    if not grounding_path.exists():
        return {}

    grounding: dict[str, RecipeNutrition] = {}
    with grounding_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            grounding[row["recipe_id"]] = RecipeNutrition.model_validate(row["nutrition"])
    return grounding


def attach_grounding(
    recipes: list[Recipe], grounding: dict[str, RecipeNutrition] | None = None
) -> list[Recipe]:
    """Attach computed nutrition to each recipe by id (in place) and return the
    same list. A recipe absent from `grounding` (job hasn't run, or hasn't
    covered this recipe yet) keeps `.nutrition = None` -- never a fake 0."""
    grounding = grounding if grounding is not None else load_grounding()
    for recipe in recipes:
        recipe.nutrition = grounding.get(recipe.recipe_id)
    return recipes


def recipes_by_id(path: str | Path | None = None) -> dict[str, Recipe]:
    return {recipe.recipe_id: recipe for recipe in attach_grounding(load_recipes(path))}


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
    return attach_grounding(list(by_id.values()))
