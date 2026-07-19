"""Tests for scripts/import_corpus.py's `run_scraped_archive_reimport` --
specifically the structural rule (A1 advisor revise round, 2026-07-19):
"the import must emit the manual-release adjudication file (or HALT)
whenever a manual_adjudication row would be released -- manual quarantine
decisions may never be silently overturned by an automated run."

All fixtures are tmp_path-only; `RECIPE_DATA_PATH` is monkeypatched so this
suite never reads or writes anything under the real data/ directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.corpus_import.scraped_archive_format import render_markdown
from scripts import import_corpus

_FOODCOM_ID = "50001"
_RECIPE_ID = "imp_143aee1c60895144"  # deterministic id for foodcom_id "50001"


def _old_quarantined_recipe_row() -> dict:
    """A recipe quarantined by a human/advisor manual adjudication (never
    the automated title/instructions scans) whose CSV-era ingredient list
    is missing a 'cereal' row its own instructions reference."""
    return {
        "recipe": {
            "recipe_id": _RECIPE_ID,
            "title": "Basic Rice Dish",
            "cuisine": None,
            "meal_type": None,
            "ingredients": [
                {"name": "rice", "amount": 2.0, "unit": None, "preparation": None},
                {"name": "water", "amount": 1.0, "unit": None, "preparation": None},
                {"name": "salt", "amount": 1.0, "unit": None, "preparation": None},
            ],
            "instructions": ["Cook rice.", "Serve warm."],
            "allergens": [],
            "diet_tags": [],
            "cook_time_min": 10,
            "calories": None,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "fiber_g": None,
            "nutrition": None,
            "description": None,
            "difficulty": None,
            "servings": 1,
            "equipment": [],
            "image_url": None,
            "image_path": None,
            "source_type": "curated",
            "source_name": "Food.com (Recipes and Reviews)",
            "source_url": _FOODCOM_ID,
            "owner_user_id": None,
            "is_user_saved": False,
            "is_active": True,
        },
        "quarantine_reason": {
            "check": "manual_adjudication",
            "explanation": "test: stir in cereal, no cereal row",
        },
        "quarantined_at_utc": "2026-07-01T00:00:00Z",
    }


def _write_archive_file(archive_dir: Path) -> None:
    """The scraped archive now carries the full ingredient list, including
    the 'cereal' row missing from the old CSV -- this recipe would pass
    both automated integrity checks and be released."""
    jsonld = {
        "@context": "http://schema.org",
        "@type": "Recipe",
        "name": "Basic Rice Dish",
        "cookTime": "PT10M",
        "recipeIngredient": ["2 cups rice", "1 cup water", "1 teaspoon salt", "1/4 cup corn cereal"],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Cook rice."},
            {"@type": "HowToStep", "text": "Stir in cereal."},
            {"@type": "HowToStep", "text": "Serve warm."},
        ],
        "recipeYield": "4 serving(s)",
    }
    meta = {
        "foodcom_id": _FOODCOM_ID,
        "recipe_id": _RECIPE_ID,
        "corpus": "quarantined",
        "url": f"https://www.food.com/recipe/example-{_FOODCOM_ID}",
        "fetched_at_utc": "2026-07-18T19:25:55Z",
        "http_status": "200",
    }
    markdown = render_markdown(jsonld, meta)
    (archive_dir / f"{_FOODCOM_ID}.md").write_text(markdown, encoding="utf-8", newline="\n")


@pytest.fixture
def _isolated_corpus(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Builds a minimal old corpus (one manual_adjudication-quarantined
    recipe, zero active recipes) + a matching one-file archive dir, with
    settings.recipe_path pointed at tmp_path so the run never touches the
    real data/ directory."""
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "sample_recipes.jsonl").write_text("", encoding="utf-8")
    (processed / "imported_recipes.jsonl").write_text("", encoding="utf-8")
    (processed / "quarantined_recipes.jsonl").write_text(
        json.dumps(_old_quarantined_recipe_row()) + "\n", encoding="utf-8"
    )

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    _write_archive_file(archive_dir)

    monkeypatch.setenv("RECIPE_DATA_PATH", str(processed / "sample_recipes.jsonl"))
    get_settings.cache_clear()
    yield processed, archive_dir
    get_settings.cache_clear()


def test_unapproved_manual_release_halts_and_still_emits_adjudication_file(
    _isolated_corpus, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    processed, archive_dir = _isolated_corpus
    # Ensure the allowlist does NOT contain this id, regardless of what the
    # real production allowlist happens to hold.
    monkeypatch.setattr(import_corpus, "_ADVISOR_APPROVED_MANUAL_RELEASES", {})

    rc = import_corpus.run_scraped_archive_reimport(str(archive_dir), no_reindex=True)

    assert rc == 1
    # Corpus/sidecar are untouched.
    assert (processed / "imported_recipes.jsonl").read_text(encoding="utf-8") == ""
    assert _RECIPE_ID in (processed / "quarantined_recipes.jsonl").read_text(encoding="utf-8")

    adjudication_files = list((processed / "quarantine_history").glob("manual_release_adjudication_*.md"))
    assert len(adjudication_files) == 1
    content = adjudication_files[0].read_text(encoding="utf-8")
    assert _RECIPE_ID in content
    assert "NOT PRE-APPROVED" in content
    assert "RELEASE JUSTIFIED" not in content

    captured = capsys.readouterr()
    assert "HALT" in captured.out
    assert "manual_adjudication" in captured.out.lower() or "NOT pre-approved" in captured.out


def test_approved_manual_release_proceeds_and_writes_justified_verdict(
    _isolated_corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    processed, archive_dir = _isolated_corpus
    monkeypatch.setattr(
        import_corpus,
        "_ADVISOR_APPROVED_MANUAL_RELEASES",
        {_RECIPE_ID: "test: cereal row now present ('corn cereal')"},
    )

    rc = import_corpus.run_scraped_archive_reimport(str(archive_dir), no_reindex=True)

    assert rc == 0
    written = [
        json.loads(line) for line in (processed / "imported_recipes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["recipe_id"] for row in written] == [_RECIPE_ID]

    adjudication_files = list((processed / "quarantine_history").glob("manual_release_adjudication_*.md"))
    assert len(adjudication_files) == 1
    content = adjudication_files[0].read_text(encoding="utf-8")
    assert _RECIPE_ID in content
    assert "RELEASE JUSTIFIED" in content
    assert "NOT PRE-APPROVED" not in content


def test_no_manual_release_case_writes_no_adjudication_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run with nothing in the manual_adjudication-released bucket must
    not emit a manual_release_adjudication file at all."""
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "sample_recipes.jsonl").write_text("", encoding="utf-8")
    (processed / "imported_recipes.jsonl").write_text("", encoding="utf-8")
    (processed / "quarantined_recipes.jsonl").write_text("", encoding="utf-8")

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    _write_archive_file(archive_dir)  # not previously quarantined at all -> lands as still_active-ish/new-only

    monkeypatch.setenv("RECIPE_DATA_PATH", str(processed / "sample_recipes.jsonl"))
    get_settings.cache_clear()
    try:
        import_corpus.run_scraped_archive_reimport(str(archive_dir), no_reindex=True)
    finally:
        get_settings.cache_clear()

    adjudication_files = list((processed / "quarantine_history").glob("manual_release_adjudication_*.md"))
    assert adjudication_files == []
