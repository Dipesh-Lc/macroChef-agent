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


def load_restored_recipe_ids(ledger_dir: str | Path | None = None) -> set[str]:
    """IDs of recipes released from quarantine by a scraped-archive reimport
    (task A1, 2026-07-19) -- the deterministic source for the "Restored from
    source" display badge (roadmap item B6).

    Reads every `scraped_archive_reimport_ledger_*.jsonl` sidecar next to the
    imported corpus (written by `scripts/import_corpus.py`'s
    `run_scraped_archive_reimport`) and unions the `recipe_id`s tagged
    `bucket == "released"` -- a recipe that was quarantined under the prior
    corpus and whose scraped-archive candidate cleared every integrity/safety
    check on reimport. No ledger files present (e.g. a fresh checkout without
    the corpus-rebuild history, or a test's isolated tmp_path) is not an
    error -- it just means no recipe gets the badge.
    """
    settings = get_settings()
    directory = Path(ledger_dir) if ledger_dir else Path(settings.recipe_path).parent
    restored: set[str] = set()
    if not directory.exists():
        return restored
    for ledger_path in sorted(directory.glob("scraped_archive_reimport_ledger_*.jsonl")):
        with ledger_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("bucket") == "released" and row.get("recipe_id"):
                    restored.add(row["recipe_id"])
    return restored


def attach_restoration(
    recipes: list[Recipe], restored_ids: set[str] | None = None
) -> list[Recipe]:
    """Set `.restored_from_quarantine` on each recipe (in place) and return
    the same list -- mirrors `attach_grounding`'s shape. A recipe absent from
    `restored_ids` (never quarantined, or quarantined but never released)
    keeps the schema default of `False`."""
    restored_ids = restored_ids if restored_ids is not None else load_restored_recipe_ids()
    for recipe in recipes:
        recipe.restored_from_quarantine = recipe.recipe_id in restored_ids
    return recipes


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
    imported_resolved = Path(imported_path) if imported_path is not None else imported_default
    imported = load_recipes(imported_resolved)

    by_id: dict[str, Recipe] = {}
    for recipe in imported:
        by_id[recipe.recipe_id] = recipe
    for recipe in seeds:
        by_id[recipe.recipe_id] = recipe
    recipes = attach_grounding(list(by_id.values()))
    # Ledgers live next to the imported corpus -- derive from the actually
    # resolved imported_path (not just the settings default) so an isolated
    # test corpus never picks up a real repo's ledger files.
    return attach_restoration(recipes, load_restored_recipe_ids(imported_resolved.parent))
