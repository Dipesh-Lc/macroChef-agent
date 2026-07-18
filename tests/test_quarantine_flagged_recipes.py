"""Tests for scripts/quarantine_flagged_recipes.py's quarantine-sidecar
MERGE behavior.

Regression coverage for the historical data-destroying bug: the script used
to REWRITE `quarantined_recipes.jsonl` from scratch on every run instead of
merging into it, which once silently clobbered a 177-row safety audit trail
down to 9 rows on a later batch run (recovered from git history). The fix
makes every run merge its newly-flagged records into whatever is already on
disk, keyed by recipe id, with the first quarantine decision always winning
and the write done atomically (temp file + os.replace).

All fixtures are tmp_path-only. This suite never reads or writes anything
under data/ or app/, and never invokes the script against real corpus data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.services.corpus_import.title_ingredient_integrity import Mismatch, build_quarantine_record
from scripts.quarantine_flagged_recipes import (
    _CHECKS,
    _load_existing_quarantine,
    _merge_quarantine_records,
    _write_quarantine_atomic,
    main,
)


def _mismatched_recipe(recipe_id: str, title: str = "Curried Peanut Shrimp") -> Recipe:
    """A recipe whose title implies an allergen (peanut) that is present in
    neither its ingredients nor its allergens field -- guaranteed to be
    flagged by the title/ingredient integrity check."""
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        ingredients=[
            Ingredient(name="shrimp", amount=1, unit=None),
            Ingredient(name="curry powder", amount=1, unit=None),
        ],
        instructions=["Cook.", "Serve."],
        allergens=[],
    )


def _quarantine_record(recipe_id: str, title: str = "Curried Peanut Shrimp", category: str = "peanut") -> dict:
    """Build a well-formed quarantine sidecar record directly (bypassing the
    audit scan) so merge-logic tests have full, deterministic control over
    the record's id and content."""
    recipe = _mismatched_recipe(recipe_id, title=title)
    mismatch = Mismatch(recipe_id=recipe_id, title=title, category=category, title_terms=[category])
    return build_quarantine_record(recipe, [mismatch])


def _write_corpus_jsonl(path: Path, recipes: list[Recipe]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for recipe in recipes:
            handle.write(json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")


def _read_quarantine(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run_script(monkeypatch, corpus_path: Path, quarantine_path: Path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quarantine_flagged_recipes.py",
            "--corpus-path",
            str(corpus_path),
            "--quarantine-path",
            str(quarantine_path),
        ],
    )
    exit_code = main()
    assert exit_code == 0


# --- (a) fresh run creates the sidecar --------------------------------------


def test_fresh_run_creates_sidecar(tmp_path, monkeypatch):
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    _write_corpus_jsonl(corpus_path, [_mismatched_recipe("r1")])

    assert not quarantine_path.exists()
    _run_script(monkeypatch, corpus_path, quarantine_path)

    rows = _read_quarantine(quarantine_path)
    assert len(rows) == 1
    assert rows[0]["recipe"]["recipe_id"] == "r1"


# --- (b) second run with new ids preserves prior rows and appends new ones --


def test_second_run_preserves_prior_rows_and_appends_new(tmp_path, monkeypatch):
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"

    _write_corpus_jsonl(corpus_path, [_mismatched_recipe("r1")])
    _run_script(monkeypatch, corpus_path, quarantine_path)
    rows_after_first = _read_quarantine(quarantine_path)
    assert {row["recipe"]["recipe_id"] for row in rows_after_first} == {"r1"}

    # r1 was removed from corpus_path by the first run (only non-flagged
    # recipes are kept); simulate a later import batch that adds a
    # DIFFERENT newly-flagged recipe to the corpus.
    _write_corpus_jsonl(corpus_path, [_mismatched_recipe("r2")])
    _run_script(monkeypatch, corpus_path, quarantine_path)

    rows_after_second = _read_quarantine(quarantine_path)
    ids = {row["recipe"]["recipe_id"] for row in rows_after_second}
    assert ids == {"r1", "r2"}

    # r1's original row survives byte-for-byte (not merely "an r1 row exists").
    original_r1 = next(row for row in rows_after_first if row["recipe"]["recipe_id"] == "r1")
    preserved_r1 = next(row for row in rows_after_second if row["recipe"]["recipe_id"] == "r1")
    assert preserved_r1 == original_r1


# --- (c) re-flagging an existing id does not duplicate or alter its row -----


def test_reflagging_existing_id_keeps_first_decision_and_does_not_duplicate(tmp_path, capsys):
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    original_record = _quarantine_record("r1", title="Curried Peanut Shrimp", category="peanut")
    _write_quarantine_atomic(quarantine_path, [original_record])

    # A later run re-flags the SAME id, but (e.g. because the corpus was
    # reset/reimported, or the detection rules changed) with a DIFFERENT
    # reason -- the merge must still keep the ORIGINAL row untouched.
    reflagged_record = _quarantine_record("r1", title="Roasted Almond Chicken", category="tree_nut")

    existing = _load_existing_quarantine(quarantine_path)
    assert set(existing) == {"r1"}

    merged, skipped = _merge_quarantine_records(existing, [reflagged_record])

    assert skipped == 1
    assert len(merged) == 1
    assert merged[0] == original_record
    assert merged[0]["quarantine_reason"]["mismatches"][0]["category"] == "peanut"

    captured = capsys.readouterr()
    assert "r1" in captured.out
    assert "already in the quarantine sidecar" in captured.out


def test_reflagging_existing_id_via_full_script_run_does_not_duplicate(tmp_path, monkeypatch):
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    original_record = _quarantine_record("r1", title="Curried Peanut Shrimp", category="peanut")
    _write_quarantine_atomic(quarantine_path, [original_record])

    # Simulate the same recipe id reappearing in a fresh corpus file (e.g. a
    # reimport) and getting flagged again by this run's audit.
    _write_corpus_jsonl(corpus_path, [_mismatched_recipe("r1")])
    _run_script(monkeypatch, corpus_path, quarantine_path)

    rows = _read_quarantine(quarantine_path)
    assert len(rows) == 1
    assert rows[0] == original_record


# --- (d) historical clobber scenario: no row loss on merge -------------------


def test_historical_clobber_scenario_no_row_loss(tmp_path, monkeypatch):
    """Regression test for the exact incident this fix addresses: a large
    batch of already-quarantined rows (standing in for the real 177
    direct-term rows) must survive completely intact when a later run
    quarantines a smaller new batch (standing in for the real 9
    derivative-term rows) -- total count must be the SUM, never a
    replacement."""
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"

    prior_batch = [_quarantine_record(f"prior-{i}", title=f"Prior Flagged Recipe {i}") for i in range(20)]
    _write_quarantine_atomic(quarantine_path, prior_batch)
    assert len(_read_quarantine(quarantine_path)) == 20

    new_batch_recipes = [_mismatched_recipe(f"new-{i}", title=f"Curried Peanut Shrimp {i}") for i in range(5)]
    _write_corpus_jsonl(corpus_path, new_batch_recipes)
    _run_script(monkeypatch, corpus_path, quarantine_path)

    rows = _read_quarantine(quarantine_path)
    ids = {row["recipe"]["recipe_id"] for row in rows}

    assert len(rows) == 25, "no row loss: 20 prior + 5 new must both be present"
    assert ids == {f"prior-{i}" for i in range(20)} | {f"new-{i}" for i in range(5)}

    # Every prior row is byte-for-byte unchanged.
    prior_by_id = {row["recipe"]["recipe_id"]: row for row in prior_batch}
    for row in rows:
        recipe_id = row["recipe"]["recipe_id"]
        if recipe_id in prior_by_id:
            assert row == prior_by_id[recipe_id]


# --- atomic write: no partial file left behind on failure --------------------


def test_write_quarantine_atomic_leaves_no_temp_file_on_success(tmp_path):
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    _write_quarantine_atomic(quarantine_path, [_quarantine_record("r1")])

    leftover_temp_files = [p for p in tmp_path.iterdir() if p.name.startswith(".quarantined_recipes.jsonl.")]
    assert leftover_temp_files == []
    assert quarantine_path.exists()


# --- --check {title,instructions} extension ---------------------------------


def _instructions_flagged_recipe(recipe_id: str) -> Recipe:
    """A recipe whose instructions name a Tier A hazard (meat: "beef") that
    is absent from both its ingredients and its allergens field -- flagged
    by the instructions check but NOT the title check (the title has no
    allergen/meat word at all)."""
    return Recipe(
        recipe_id=recipe_id,
        title="Weeknight Stir-Fry",
        ingredients=[Ingredient(name="broccoli", amount=1, unit=None)],
        instructions=["Slice the beef thinly.", "Stir-fry with broccoli."],
        allergens=[],
    )


def _tier_c_only_recipe(recipe_id: str) -> Recipe:
    """A recipe with ONLY a Tier C (report-only) instructions mismatch --
    must NEVER be selected for quarantine by --check instructions."""
    return Recipe(
        recipe_id=recipe_id,
        title="Simple Saute",
        ingredients=[Ingredient(name="broccoli", amount=1, unit=None)],
        instructions=["Heat the oil in a pan.", "Add broccoli and stir-fry."],
        allergens=[],
    )


def test_default_check_is_title_backward_compatible(tmp_path, monkeypatch):
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    _write_corpus_jsonl(corpus_path, [_mismatched_recipe("r1")])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quarantine_flagged_recipes.py",
            "--corpus-path",
            str(corpus_path),
            "--quarantine-path",
            str(quarantine_path),
        ],
    )
    assert main() == 0

    rows = _read_quarantine(quarantine_path)
    assert len(rows) == 1
    assert rows[0]["quarantine_reason"]["check"] == "title_ingredient_integrity"


def test_check_instructions_flags_a_row_the_title_check_misses(tmp_path, monkeypatch):
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    _write_corpus_jsonl(corpus_path, [_instructions_flagged_recipe("r1")])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quarantine_flagged_recipes.py",
            "--corpus-path",
            str(corpus_path),
            "--quarantine-path",
            str(quarantine_path),
            "--check",
            "instructions",
        ],
    )
    assert main() == 0

    rows = _read_quarantine(quarantine_path)
    assert len(rows) == 1
    assert rows[0]["recipe"]["recipe_id"] == "r1"
    assert rows[0]["quarantine_reason"]["check"] == "instructions_ingredient_integrity"
    assert rows[0]["quarantine_reason"]["mismatches"][0]["category"] == "meat"
    assert rows[0]["quarantine_reason"]["mismatches"][0]["tier"] == "A"

    remaining_corpus = json.loads(corpus_path.read_text(encoding="utf-8")) if corpus_path.read_text(
        encoding="utf-8"
    ).strip() else []
    assert remaining_corpus == []


def test_check_instructions_never_quarantines_tier_c_only_row(tmp_path, monkeypatch):
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    _write_corpus_jsonl(corpus_path, [_tier_c_only_recipe("r1")])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quarantine_flagged_recipes.py",
            "--corpus-path",
            str(corpus_path),
            "--quarantine-path",
            str(quarantine_path),
            "--check",
            "instructions",
        ],
    )
    assert main() == 0

    # A Tier-C-only ("oil") mismatch must never select a row for quarantine.
    assert _read_quarantine(quarantine_path) == []
    remaining_ids = {
        json.loads(line)["recipe_id"]
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert remaining_ids == {"r1"}


def test_check_title_still_ignores_instructions_only_mismatch(tmp_path, monkeypatch):
    # The SAME row that --check instructions flags must be left alone by
    # the default --check title (no title-side allergen word at all).
    corpus_path = tmp_path / "imported_recipes.jsonl"
    quarantine_path = tmp_path / "quarantined_recipes.jsonl"
    _write_corpus_jsonl(corpus_path, [_instructions_flagged_recipe("r1")])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quarantine_flagged_recipes.py",
            "--corpus-path",
            str(corpus_path),
            "--quarantine-path",
            str(quarantine_path),
            "--check",
            "title",
        ],
    )
    assert main() == 0
    assert _read_quarantine(quarantine_path) == []


def test_checks_registry_has_exactly_title_and_instructions() -> None:
    assert set(_CHECKS) == {"title", "instructions"}
