"""Tests for CorpusImportPipeline's title/ingredient integrity check --
the import-time guard against the 2026-07 corpus safety finding recurring
in a future import (see app.services.corpus_import.title_ingredient_integrity).

Uses a dedicated fixture CSV so this suite doesn't depend on / interfere
with tests/fixtures/corpus_sample.csv (owned by test_corpus_import.py).
"""

import json
from pathlib import Path

import pytest

from app.services.corpus_import import pipeline as pipeline_module
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


# --- Instructions/ingredient integrity check, wired at import time ---------
# (app.services.corpus_import.instructions_ingredient_integrity,
# docs/instructions_integrity_spec.md)


def _write_instructions_defect_fixture(tmp_path: Path) -> Path:
    csv_text = (
        "RecipeId,Name,CookTime,RecipeServings,RecipeCategory,"
        "RecipeIngredientParts,RecipeIngredientQuantities,RecipeInstructions,"
        "Calories,ProteinContent,CarbohydrateContent,FatContent,FiberContent\n"
        # Title has no allergen/meat word at all (so the TITLE check leaves
        # it alone), but instructions name "beef" -- zero animal-flesh
        # ingredient rows -- a Tier A "meat" mismatch.
        '4001,Weeknight Stir-Fry,PT15M,2,dinner,'
        '"c(""broccoli"", ""garlic"", ""ginger"")",'
        '"c(""1"", ""1"", ""1"")",'
        '"c(""Slice the beef thinly."", ""Stir-fry with broccoli."")",'
        "300,20,10,12,3\n"
        # Clean control row: chicken IS listed, so "chicken" in instructions
        # is satisfied -- must survive.
        '4002,Simple Chicken Dinner,PT20M,2,dinner,'
        '"c(""chicken breast"", ""broccoli"", ""garlic"")",'
        '"c(""1"", ""1"", ""1"")",'
        '"c(""Cook the chicken."", ""Add broccoli and serve."")",'
        "350,30,10,15,3\n"
    )
    path = tmp_path / "corpus_sample_instructions_integrity.csv"
    path.write_text(csv_text, encoding="utf-8")
    return path


def test_instructions_ingredient_mismatch_is_quarantined_not_written(tmp_path: Path) -> None:
    fixture = _write_instructions_defect_fixture(tmp_path)
    pipeline = CorpusImportPipeline(FoodComAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"

    report = pipeline.run(fixture, output_path, existing_recipes=[])

    assert report.survivors == 1
    assert report.instructions_ingredient_mismatches_flagged == 1
    assert report.instructions_ingredient_mismatch_pairs == 1
    # The title check never fires for this row (no title-side allergen word).
    assert report.title_ingredient_mismatches_flagged == 0

    written = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    titles = {row["title"] for row in written}
    assert titles == {"Simple Chicken Dinner"}
    assert "Weeknight Stir-Fry" not in titles

    quarantine_path = output_path.parent / "quarantined_recipes.jsonl"
    quarantined = [json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines()]
    assert len(quarantined) == 1
    assert quarantined[0]["recipe"]["title"] == "Weeknight Stir-Fry"
    assert quarantined[0]["quarantine_reason"]["check"] == "instructions_ingredient_integrity"
    assert quarantined[0]["quarantine_reason"]["mismatches"][0]["category"] == "meat"
    assert quarantined[0]["quarantine_reason"]["mismatches"][0]["tier"] == "A"


# --- Atomic quarantine-sidecar write (pipeline._write_quarantine_jsonl) ----
# A1 (2026-07-19): ported the temp-file + os.replace pattern from
# scripts/quarantine_flagged_recipes.py's _write_quarantine_atomic so a
# crash/interruption partway through writing the sidecar for a 4,235-file
# archive re-import can never truncate the file already on disk.


def test_interrupted_quarantine_write_never_truncates_existing_sidecar(tmp_path: Path, monkeypatch) -> None:
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    original_contents = '{"recipe": {"recipe_id": "imp_existing"}}\n'
    quarantine_path.write_text(original_contents, encoding="utf-8")

    class BoomError(Exception):
        pass

    real_dumps = pipeline_module.json.dumps
    calls = {"n": 0}

    def flaky_dumps(obj, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:  # blow up partway through a multi-record write
            raise BoomError("simulated crash mid-write")
        return real_dumps(obj, **kwargs)

    monkeypatch.setattr(pipeline_module.json, "dumps", flaky_dumps)

    new_records = [{"recipe": {"recipe_id": "imp_a"}}, {"recipe": {"recipe_id": "imp_b"}}]
    with pytest.raises(BoomError):
        pipeline_module._write_quarantine_jsonl(quarantine_path, new_records)

    # The real file at quarantine_path is untouched -- os.replace() only
    # ever happens after the temp file is fully written.
    assert quarantine_path.read_text(encoding="utf-8") == original_contents
    # No leftover temp file either.
    leftovers = list(tmp_path.glob(f".{quarantine_path.name}.*.tmp"))
    assert leftovers == []


def test_quarantine_write_succeeds_atomically_on_the_happy_path(tmp_path: Path) -> None:
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    records = [{"recipe": {"recipe_id": "imp_a"}}, {"recipe": {"recipe_id": "imp_b"}}]
    pipeline_module._write_quarantine_jsonl(quarantine_path, records)

    written = [json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines()]
    assert written == records
    assert list(tmp_path.glob(f".{quarantine_path.name}.*.tmp")) == []
