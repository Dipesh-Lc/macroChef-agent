"""Tests for `FoodComScrapedArchiveAdapter` (app.services.corpus_import.adapters) --
the adapter that reads the scraped Food.com archive (data/scraped/foodcom/*.md)
instead of the original Kaggle CSV. See tests/fixtures/foodcom_scraped_sample/
for the fixture files these tests exercise (generated with the real
`render_markdown` writer so the format matches the live archive byte-for-byte;
9002/9003/9004/9005 are then hand-corrupted for the specific hard-abort case
each test covers)."""

import pytest

from app.services.corpus_import.adapters import (
    FoodComScrapedArchiveAdapter,
    ScrapedArchiveIntegrityError,
)
from app.services.corpus_import.pipeline import CorpusImportPipeline

FIXTURE_DIR = "tests/fixtures/foodcom_scraped_sample"
PIPELINE_FIXTURE_DIR = "tests/fixtures/foodcom_scraped_pipeline_sample"


def _read_one(filename: str) -> dict:
    """Read a single fixture file directly via the adapter's private reader,
    bypassing the glob over the whole fixture directory (which contains
    several files deliberately broken in different ways -- each test wants
    only its own file)."""
    from pathlib import Path

    from app.services.corpus_import.adapters import _read_scraped_archive_file

    return _read_scraped_archive_file(Path(FIXTURE_DIR) / filename, FoodComScrapedArchiveAdapter.dataset_name)


def test_valid_file_reads_and_converts() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)

    assert candidate is not None
    assert candidate.title == "S&W&reg; Black Bean Chili"  # single-pass html.unescape
    assert candidate.source_url == "9001"
    assert candidate.cuisine is None
    assert candidate.cook_time_min == 20
    assert candidate.calories == 320
    assert candidate.protein_g == 12
    assert candidate.carbs_g == 40
    assert candidate.fat_g == 10
    assert candidate.fiber_g == 8


def test_id_mismatch_hard_aborts() -> None:
    """9002.md's frontmatter recipe_id is deliberately 9001's id, not its
    own -- read_raw must raise, never silently skip or accept it."""
    with pytest.raises(ScrapedArchiveIntegrityError, match="recipe_id mismatch"):
        _read_one("9002.md")


def test_bad_http_status_hard_aborts() -> None:
    with pytest.raises(ScrapedArchiveIntegrityError, match="http_status"):
        _read_one("9003.md")


def test_bad_scraper_version_hard_aborts() -> None:
    with pytest.raises(ScrapedArchiveIntegrityError, match="scraper_version"):
        _read_one("9004.md")


def test_unparseable_json_hard_aborts() -> None:
    with pytest.raises(ScrapedArchiveIntegrityError, match="unparseable JSON"):
        _read_one("9005.md")


def test_servings_leading_integer_of_yield_string() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)
    assert candidate.servings == 8  # "8 serving(s)" -> leading int 8


def test_servings_no_leading_digit_falls_back_to_one_with_counter() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    assert adapter._parse_servings("Makes a big batch") == 1
    assert adapter.servings_no_leading_digit == 1


def test_servings_zero_coerced_to_one_with_counter() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    assert adapter._parse_servings("0 serving(s)") == 1
    assert adapter.servings_coerced_from_zero == 1


def test_pack_size_ingredient_line_keeps_full_name() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)
    ingredient = next(item for item in candidate.ingredients if "black beans" in item.name)
    assert ingredient.name == "black beans, rinsed and drained"
    assert ingredient.amount == 15.0
    assert ingredient.unit == "oz"


def test_parenthetical_ingredient_reaches_allergen_derivation_unstripped() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)
    butter = next(item for item in candidate.ingredients if item.name.startswith("butter"))
    assert butter.name == "butter (cut into pieces)"  # parenthetical kept, unstripped
    assert "dairy" in candidate.allergens


def test_entity_unescaped_in_title() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)
    assert "&amp;" not in candidate.title
    assert candidate.title == "S&W&reg; Black Bean Chili"


# --- Advisor revise round (2026-07-19): meal_type mapping + instruction
# html.unescape were both missed by the original spec/first pass. ---


def test_recipe_category_dessert_maps_to_meal_type() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9010.md")
    candidate = adapter.to_candidate(raw)
    assert candidate.meal_type == "dessert"


def test_unmapped_recipe_category_yields_none_meal_type() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9011.md")
    candidate = adapter.to_candidate(raw)
    assert candidate.meal_type is None


def test_missing_recipe_category_yields_none_meal_type() -> None:
    # 9001.md's JSON-LD carries no recipeCategory field at all.
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)
    assert candidate.meal_type is None


def test_instruction_html_entity_unescaped_before_cleaning() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9010.md")
    candidate = adapter.to_candidate(raw)
    assert "Preheat oven & grease pan." in candidate.instructions
    assert not any("&amp;" in step for step in candidate.instructions)


def test_bare_string_instruction_item_handled() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)
    assert "Add beans and broth." in candidate.instructions


def test_missing_text_step_skipped_and_counted() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    raw = _read_one("9001.md")
    candidate = adapter.to_candidate(raw)

    # 4 raw steps in the fixture; one HowToStep has no "text" key at all.
    assert len(candidate.instructions) == 3
    assert adapter.instructions_missing_text_dropped == 1
    assert adapter.recipes_with_missing_text_steps == 1


# --- Pipeline-level per-id ledger tracking (dry_run + foodcom_id-keyed
# bucket lists) -- exercised over tests/fixtures/foodcom_scraped_pipeline_sample,
# a small ALL-VALID (integrity-check-wise) archive dir covering the three
# ways a candidate can be dropped before ever getting a recipe_id minted:
# 9006 (blank title -> adapter-rejected), 9007/9008 (exact-title duplicate
# pair -> 9008 is the duplicate), 9009 (1 instruction step -> fails
# RecipeValidationService's 2-step minimum), plus 9001 (a normal survivor).


def test_dry_run_writes_nothing_but_populates_full_report(tmp_path) -> None:
    pipeline = CorpusImportPipeline(FoodComScrapedArchiveAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"

    report = pipeline.run(
        PIPELINE_FIXTURE_DIR,
        output_path,
        existing_recipes=[],
        quarantine_path=quarantine_path,
        dry_run=True,
    )

    assert not output_path.exists()
    assert not quarantine_path.exists()
    assert report.read == 5
    # 9001 and 9007 (first of the 9007/9008 duplicate-title pair) survive;
    # 9006 (adapter-rejected), 9008 (duplicate of 9007), 9009 (failed
    # validation) do not.
    assert report.survivors == 2
    assert sorted(r.recipe_id for r in report.recipes) == sorted(
        ["imp_d1ba26f5480759cb", "imp_5df4df6d69605748"]
    )


def test_ledger_tracking_ids_by_bucket(tmp_path) -> None:
    pipeline = CorpusImportPipeline(FoodComScrapedArchiveAdapter())
    output_path = tmp_path / "imported_recipes.jsonl"

    report = pipeline.run(PIPELINE_FIXTURE_DIR, output_path, existing_recipes=[], dry_run=True)

    assert report.rejected_by_adapter == 1
    assert report.rejected_by_adapter_source_ids == ["9006"]

    assert report.failed_validation == 1
    assert report.failed_validation_candidate_ids == ["foodcom_scraped_9009"]

    assert report.duplicates == 1
    assert report.duplicate_candidate_ids == ["foodcom_scraped_9008"]


def test_pipeline_write_after_dry_run_matches_a_direct_write(tmp_path) -> None:
    """`pipeline.write(...)` after a `dry_run=True` call must produce the
    exact same on-disk files as a normal (non-dry-run) `run()` call over
    the same source -- this is the write-after-dry-run pattern the archive
    re-import migration relies on to avoid running the pipeline twice."""
    dry_pipeline = CorpusImportPipeline(FoodComScrapedArchiveAdapter())
    dry_output = tmp_path / "dry" / "imported_recipes.jsonl"
    dry_quarantine = tmp_path / "dry" / "quarantined_recipes.jsonl"
    report = dry_pipeline.run(
        PIPELINE_FIXTURE_DIR, dry_output, existing_recipes=[], quarantine_path=dry_quarantine, dry_run=True
    )
    assert not dry_output.exists()
    dry_pipeline.write(dry_output, dry_quarantine, report)
    assert dry_output.exists()
    assert dry_quarantine.exists()

    direct_pipeline = CorpusImportPipeline(FoodComScrapedArchiveAdapter())
    direct_output = tmp_path / "direct" / "imported_recipes.jsonl"
    direct_quarantine = tmp_path / "direct" / "quarantined_recipes.jsonl"
    direct_pipeline.run(
        PIPELINE_FIXTURE_DIR, direct_output, existing_recipes=[], quarantine_path=direct_quarantine, dry_run=False
    )

    assert dry_output.read_text(encoding="utf-8") == direct_output.read_text(encoding="utf-8")
    assert dry_quarantine.read_text(encoding="utf-8") == direct_quarantine.read_text(encoding="utf-8")


def test_read_raw_over_directory_sorted_and_skips_nothing_but_md() -> None:
    adapter = FoodComScrapedArchiveAdapter()
    # Only 9001.md is fully valid in this fixture dir; reading the whole
    # directory must raise on the first broken file it encounters (sorted
    # numerically, so 9001 first, then whichever broken file sorts next) --
    # this proves read_raw doesn't swallow a broken file into a skip.
    with pytest.raises(ScrapedArchiveIntegrityError):
        list(adapter.read_raw(FIXTURE_DIR))
