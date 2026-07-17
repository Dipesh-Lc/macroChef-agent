"""Tests for CorpusImportPipeline's title/ingredient integrity check --
the import-time guard against the 2026-07 corpus safety finding recurring
in a future import (see app.services.corpus_import.title_ingredient_integrity).

Uses a dedicated fixture CSV so this suite doesn't depend on / interfere
with tests/fixtures/corpus_sample.csv (owned by test_corpus_import.py).
"""

import json
from pathlib import Path

from app.services.corpus_import.adapters import FoodComAdapter
from app.services.corpus_import.pipeline import CorpusImportPipeline

FIXTURE = Path(__file__).parent / "fixtures" / "corpus_sample_title_integrity.csv"

# Fixture rows, deliberately covering:
#   2001 Crab Dip           -- title implies crustacean, ingredients have NONE
#                              (mirrors the real "Curried Peanut Shrimp" defect)
#   2002 Peanut Noodles     -- title implies peanut, ingredients genuinely have it (clean)


def _write_fixture(tmp_path: Path) -> Path:
    csv_text = (
        "RecipeId,Name,CookTime,RecipeServings,RecipeCategory,"
        "RecipeIngredientParts,RecipeIngredientQuantities,RecipeInstructions,"
        "Calories,ProteinContent,CarbohydrateContent,FatContent,FiberContent\n"
        '2001,Crab Dip,PT10M,4,snack,'
        '"c(""cream cheese"", ""green onions"", ""sherry wine"")",'
        '"c(""8"", ""2"", ""1"")",'
        '"c(""Mix ingredients."", ""Chill and serve."")",'
        "200,4,5,15,1\n"
        '2002,Peanut Noodles,PT20M,2,dinner,'
        '"c(""peanut butter"", ""noodles"", ""soy sauce"")",'
        '"c(""2"", ""8"", ""1"")",'
        '"c(""Boil noodles."", ""Mix sauce."", ""Combine."")",'
        "520,18,60,20,4\n"
    )
    path = tmp_path / "corpus_sample_title_integrity.csv"
    path.write_text(csv_text, encoding="utf-8")
    return path


def test_title_ingredient_mismatch_is_quarantined_not_written(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    pipeline = CorpusImportPipeline(FoodComAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"

    report = pipeline.run(fixture, output_path, existing_recipes=[])

    # "Crab Dip" (no crab ingredient) is quarantined, not written; "Peanut
    # Noodles" (peanut butter genuinely present) survives normally.
    assert report.survivors == 1
    assert report.title_ingredient_mismatches_flagged == 1
    assert report.title_ingredient_mismatch_pairs == 1

    written = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    titles = {row["title"] for row in written}
    assert titles == {"Peanut Noodles"}
    assert "Crab Dip" not in titles

    quarantine_path = output_path.parent / "quarantined_recipes.jsonl"
    assert quarantine_path.exists()
    quarantined = [json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines()]
    assert len(quarantined) == 1
    assert quarantined[0]["recipe"]["title"] == "Crab Dip"
    assert quarantined[0]["quarantine_reason"]["check"] == "title_ingredient_integrity"
    assert quarantined[0]["quarantine_reason"]["mismatches"][0]["category"] == "crustacean"


def test_clean_import_writes_empty_quarantine_file(tmp_path: Path) -> None:
    """A run where nothing is flagged still writes an (empty) quarantine
    sidecar -- see pipeline._write_quarantine_jsonl's docstring for why this
    matters (a stale quarantine file from an earlier run must not survive
    at the default path when a fresh run finds nothing to quarantine)."""
    csv_text = (
        "RecipeId,Name,CookTime,RecipeServings,RecipeCategory,"
        "RecipeIngredientParts,RecipeIngredientQuantities,RecipeInstructions,"
        "Calories,ProteinContent,CarbohydrateContent,FatContent,FiberContent\n"
        '3001,Peanut Noodles,PT20M,2,dinner,'
        '"c(""peanut butter"", ""noodles"", ""soy sauce"")",'
        '"c(""2"", ""8"", ""1"")",'
        '"c(""Boil noodles."", ""Mix sauce."", ""Combine."")",'
        "520,18,60,20,4\n"
    )
    fixture = tmp_path / "clean.csv"
    fixture.write_text(csv_text, encoding="utf-8")

    pipeline = CorpusImportPipeline(FoodComAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"
    report = pipeline.run(fixture, output_path, existing_recipes=[])

    assert report.title_ingredient_mismatches_flagged == 0
    quarantine_path = output_path.parent / "quarantined_recipes.jsonl"
    assert quarantine_path.exists()
    assert quarantine_path.read_text(encoding="utf-8") == ""


def test_quarantine_path_override(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    pipeline = CorpusImportPipeline(FoodComAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"
    custom_quarantine = tmp_path / "custom_quarantine.jsonl"

    pipeline.run(fixture, output_path, existing_recipes=[], quarantine_path=custom_quarantine)

    assert custom_quarantine.exists()
    default_quarantine = output_path.parent / "quarantined_recipes.jsonl"
    assert not default_quarantine.exists()
