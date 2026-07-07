import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.rag.loaders import attach_grounding, load_corpus, load_grounding, recipes_by_id
from app.schemas.nutrition import RecipeNutrition
from app.schemas.recipe import Recipe

_MACROS = {"calories": 300, "protein_g": 20, "carbs_g": 30, "fat_g": 8, "fiber_g": 4}
_ZERO_MACROS = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}


def _write_recipe(path: Path, recipe_id: str, title: str = "T") -> None:
    path.write_text(
        json.dumps({"recipe_id": recipe_id, "title": title, "ingredients": [], "instructions": []}) + "\n",
        encoding="utf-8",
    )


def _grounding_row(recipe_id: str, *, status: str, coverage: float) -> str:
    macros = _MACROS if status != "ungrounded" else _ZERO_MACROS
    return json.dumps(
        {
            "recipe_id": recipe_id,
            "nutrition": {
                "status": status,
                "servings": 1,
                "total": macros,
                "per_serving": macros,
                "contributions": [],
                "ungrounded_ingredients": [] if status != "ungrounded" else ["x"],
                "coverage": coverage,
            },
        }
    )


def test_load_grounding_returns_empty_when_sidecar_missing(tmp_path) -> None:
    assert load_grounding(tmp_path / "does_not_exist.jsonl") == {}


def test_load_grounding_parses_sidecar_into_recipe_nutrition(tmp_path) -> None:
    path = tmp_path / "grounding.jsonl"
    path.write_text(_grounding_row("r_1", status="grounded", coverage=1.0) + "\n", encoding="utf-8")

    grounding = load_grounding(path)

    assert grounding["r_1"].status.value == "grounded"
    assert grounding["r_1"].per_serving.calories == 300


def test_attach_grounding_sets_nutrition_when_present() -> None:
    recipe = Recipe(recipe_id="r_1", title="T")
    nutrition = RecipeNutrition.model_validate(
        {"status": "grounded", "servings": 1, "total": _MACROS, "per_serving": _MACROS, "coverage": 1.0}
    )

    attach_grounding([recipe], {"r_1": nutrition})

    assert recipe.nutrition is not None
    assert recipe.nutrition.status.value == "grounded"


def test_attach_grounding_leaves_nutrition_none_when_absent_from_sidecar() -> None:
    recipe = Recipe(recipe_id="r_unknown", title="T")

    attach_grounding([recipe], {})

    assert recipe.nutrition is None


@pytest.fixture
def _isolated_recipe_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points settings.recipe_path at an isolated tmp_path seed file, so
    load_corpus()/recipes_by_id() derive their grounding-sidecar path
    (parent-of-recipe_path/grounding.jsonl) from tmp_path too."""
    seed_path = tmp_path / "sample_recipes.jsonl"
    monkeypatch.setenv("RECIPE_DATA_PATH", str(seed_path))
    get_settings.cache_clear()
    yield seed_path
    get_settings.cache_clear()


def test_load_corpus_attaches_grounding_to_seeds_and_imported(_isolated_recipe_path) -> None:
    seed_path = _isolated_recipe_path
    tmp_path = seed_path.parent
    imported_path = tmp_path / "imported_recipes.jsonl"
    grounding_path = tmp_path / "grounding.jsonl"

    _write_recipe(seed_path, "r_seed")
    _write_recipe(imported_path, "imp_1")
    grounding_path.write_text(
        _grounding_row("r_seed", status="grounded", coverage=1.0)
        + "\n"
        + _grounding_row("imp_1", status="ungrounded", coverage=0.0)
        + "\n",
        encoding="utf-8",
    )

    recipes = load_corpus(seed_path=seed_path, imported_path=imported_path)

    by_id = {r.recipe_id: r for r in recipes}
    assert by_id["r_seed"].nutrition.status.value == "grounded"
    assert by_id["imp_1"].nutrition.status.value == "ungrounded"


def test_recipes_by_id_attaches_grounding(_isolated_recipe_path) -> None:
    seed_path = _isolated_recipe_path
    grounding_path = seed_path.parent / "grounding.jsonl"
    _write_recipe(seed_path, "r_x")
    grounding_path.write_text(_grounding_row("r_x", status="grounded", coverage=1.0) + "\n", encoding="utf-8")

    by_id = recipes_by_id(seed_path)

    assert by_id["r_x"].nutrition.status.value == "grounded"
