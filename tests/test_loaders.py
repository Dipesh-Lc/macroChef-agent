import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.rag.loaders import (
    attach_grounding,
    attach_restoration,
    load_corpus,
    load_grounding,
    load_restored_recipe_ids,
    recipes_by_id,
)
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


# --- B6: "Restored from source" badge (recipe.restored_from_quarantine) -----


def _ledger_row(recipe_id: str, bucket: str) -> str:
    return json.dumps({"bucket": bucket, "recipe_id": recipe_id, "was_active_before": False})


def test_load_restored_recipe_ids_returns_empty_when_no_ledger_files(tmp_path) -> None:
    assert load_restored_recipe_ids(tmp_path) == set()


def test_load_restored_recipe_ids_returns_empty_when_dir_missing(tmp_path) -> None:
    assert load_restored_recipe_ids(tmp_path / "does_not_exist") == set()


def test_load_restored_recipe_ids_unions_released_bucket_across_ledger_files(tmp_path) -> None:
    (tmp_path / "scraped_archive_reimport_ledger_20260101T000000Z.jsonl").write_text(
        "\n".join(
            [
                _ledger_row("imp_restored_1", "released"),
                _ledger_row("imp_still_quarantined", "still_quarantined"),
                _ledger_row("imp_still_active", "still_active"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "scraped_archive_reimport_ledger_20260102T000000Z.jsonl").write_text(
        _ledger_row("imp_restored_2", "released") + "\n",
        encoding="utf-8",
    )
    # A non-ledger file in the same directory must be ignored.
    (tmp_path / "imported_recipes.jsonl").write_text(
        json.dumps({"recipe_id": "imp_restored_1", "title": "T"}) + "\n", encoding="utf-8"
    )

    restored = load_restored_recipe_ids(tmp_path)

    assert restored == {"imp_restored_1", "imp_restored_2"}


def test_attach_restoration_sets_flag_only_for_restored_ids() -> None:
    restored_recipe = Recipe(recipe_id="imp_restored", title="T")
    normal_recipe = Recipe(recipe_id="imp_normal", title="T")

    attach_restoration([restored_recipe, normal_recipe], {"imp_restored"})

    assert restored_recipe.restored_from_quarantine is True
    assert normal_recipe.restored_from_quarantine is False


def test_load_corpus_sets_restored_badge_from_ledger(_isolated_recipe_path) -> None:
    seed_path = _isolated_recipe_path
    tmp_path = seed_path.parent
    imported_path = tmp_path / "imported_recipes.jsonl"

    _write_recipe(seed_path, "r_seed")
    with imported_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"recipe_id": "imp_restored", "title": "Restored"}) + "\n")
        handle.write(json.dumps({"recipe_id": "imp_normal", "title": "Normal"}) + "\n")
    (tmp_path / "scraped_archive_reimport_ledger_20260719T061239Z.jsonl").write_text(
        "\n".join(
            [
                _ledger_row("imp_restored", "released"),
                _ledger_row("imp_normal", "still_active"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    by_id = {r.recipe_id: r for r in load_corpus(seed_path=seed_path, imported_path=imported_path)}

    assert by_id["imp_restored"].restored_from_quarantine is True
    assert by_id["imp_normal"].restored_from_quarantine is False
    # A seed recipe (never quarantined by the import pipeline) never carries
    # the badge even if the id happened to appear in a ledger's other buckets.
    assert by_id["r_seed"].restored_from_quarantine is False
