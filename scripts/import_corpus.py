"""Import an external recipe dataset into the corpus and rebuild the index.

Usage:
    python scripts/import_corpus.py --dataset foodcom --source path/to/recipes.csv --limit 5000

Idempotent: re-running overwrites data/processed/imported_recipes.jsonl from
scratch (sorted by deterministic recipe id) and, unless --no-reindex, drops
and recreates the Chroma collection before re-indexing the union of the 25
curated seeds and the freshly imported recipes -- so a re-run with a smaller
or corrected dataset never leaves orphaned rows or stale embeddings behind.

--dataset foodcom_scraped_archive is a SEPARATE mode (task A1, 2026-07-19):
a full re-import + reconciliation against the CURRENT on-disk corpus from
the scraped Food.com archive (data/scraped/foodcom/*.md), used ONCE to
migrate the corpus off the original Kaggle CSV onto the archive as the new
source of truth. See `run_scraped_archive_reimport` below for the full
id-ledger / released / newly-quarantined / unsourced / allergen-diff /
unit-coverage reporting and the three pre-registered safety halts. Usage:

    python scripts/import_corpus.py --dataset foodcom_scraped_archive \\
        --source data/scraped/foodcom
"""

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.rag.loaders import load_recipes  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.services.constraint_engine import contains_allergen  # noqa: E402
from app.services.corpus_import.adapters import FoodComAdapter, FoodComScrapedArchiveAdapter  # noqa: E402
from app.services.corpus_import.pipeline import CorpusImportPipeline  # noqa: E402
from app.services.recipe_indexing_service import RecipeIndexingService  # noqa: E402

_ADAPTERS = {
    "foodcom": FoodComAdapter,
    "foodcom_scraped_archive": FoodComScrapedArchiveAdapter,
}

# Candidate ids minted by FoodComScrapedArchiveAdapter follow this exact
# convention (see adapters.py) -- used here to recover the original
# foodcom_id from a candidate_id reported in ImportReport.failed_validation_
# candidate_ids / duplicate_candidate_ids for the archive-reimport ledger
# below. Not meaningful for any other adapter's candidate_id convention.
_SCRAPED_CANDIDATE_ID_PREFIX = "foodcom_scraped_"

# --- Halts (A1 task spec 2026-07-19; redefined by advisor REVISE verdict
# 2026-07-19 after the first run's raw label-diff/released% halts tripped
# and were investigated) ------------------------------------------------
#
# The original label-diff-% and released-% thresholds below are RETIRED as
# hard gates (kept as constants only for the historical record / report
# text). The advisor's investigation of the 20260719T061239Z run found:
#   - all 4,314 individually lost allergen LABELS (1,982 recipes) tested
#     against `contains_allergen` itself -- the actual live query-time
#     safety gate (app.graph.nodes -> constraint_engine.validate_recipe) --
#     produced ZERO serve-time gaps: it re-scans ingredient NAMES via
#     substring matching, independent of the stored `allergens` metadata
#     field that `derive_allergen_labels`'s exact-match logic under-covers
#     on natural-language text. See docs/BACKLOG.md for the tracked
#     methodology gap in `derive_allergen_labels` itself (not fixed here).
#   - of 982 releases: 811 have the flagged term literally present in the
#     scraped rows, 159 pass a fresh recheck via category vocabulary, and
#     12 were pre-existing MANUAL adjudication quarantines, individually
#     examined and confirmed cured at source (the CSV was row-truncated) --
#     see `_ADVISOR_APPROVED_MANUAL_RELEASES` below and the
#     `manual_release_adjudication_<ts>.md` artifact this run emits.
# The new gate is the SERVE-TIME coverage check itself: not "did the
# derived label change" but "is the actual safety-relevant ingredient
# still detectable by the mechanism that decides what gets served". This
# is what removed the earlier halt's false-alarm rate.
_ALLERGEN_LOSS_HALT_FRACTION = 0.02  # retired as a hard gate; reported only
_RELEASED_HALT_FRACTION = 0.50  # retired as a hard gate for THIS source upgrade only
_NEWLY_QUARANTINED_HALT_FRACTION = 0.10  # unchanged: still a hard gate

# --- Advisor-reviewed manual-quarantine release allowlist (2026-07-19) -----
#
# `scripts/quarantine_flagged_recipes.py --recipe-ids` quarantine records
# carry `quarantine_reason.check == "manual_adjudication"` -- individually
# hand-adjudicated safety decisions (data/evaluation/
# adjudication_20260717T145539Z.md, adjudication_20260718T090522Z.md,
# adjudication_20260717T165139Z.md), never produced by the automated
# title/instructions integrity scans. A re-import "releasing" one of these
# ids because it now passes the AUTOMATED checks is NOT the same thing as a
# human re-reviewing the original manual finding -- so this run structurally
# REFUSES to silently release any manual_adjudication id that is not listed
# here, with the advisor's own cited cure evidence. Adding an id here
# without a genuine, cited, per-case review is exactly the
# "silently overturned" failure mode this allowlist exists to prevent (see
# `run_scraped_archive_reimport`'s manual-release handling below).
_ADVISOR_APPROVAL_DATE = "2026-07-19"
_ADVISOR_APPROVED_MANUAL_RELEASES: dict[str, str] = {
    "imp_2bd54fd475cf50fc": (
        "Butterscotch Chewy Bars -- original finding (adjudication_20260718T090522Z "
        "diet_023 class): instructions 'stir in cereals' with no cereal ingredient row. "
        "Cured: archive ingredients now include 'crispy rice cereal' and "
        "'corn flakes cereal'."
    ),
    "imp_348d24dd1f4d5284": (
        "Prize Butter Tarts -- original finding (adjudication_20260717T145539Z diet_023): "
        "instructions 'Prepare pastry dough... line tart pans' with no pastry ingredient "
        "row. Cured: archive ingredients now include 'pastry for double-crust pie'."
    ),
    "imp_42d786e354855c6c": (
        "Grape-Nuts Pudding -- original finding (adjudication_20260718T090522Z diet_023 "
        "class): instructions stir in undisclosed cereal, no cereal row. Cured: archive "
        "ingredients now include 'Post Grape-Nuts cereal'."
    ),
    "imp_6ab74a6c238451a3": (
        "Banana-Nut Muffins -- original finding (adjudication_20260717T145539Z macro_018): "
        "instructions 'Mix nuts with' with no nuts ingredient row. Cured: archive "
        "ingredients now include 'nuts (walnuts or pecans are good)'."
    ),
    "imp_78c1d567c07b545a": (
        "Chinese Beef and Broccoli -- original finding (adjudication_20260717T145539Z "
        "diet_015): instructions 'Slice the steak' with no steak/beef ingredient row. "
        "Cured: archive ingredients now include 'flank steak'."
    ),
    "imp_997819df41245ec6": (
        "Perfectly Spiced Banana Bread -- original finding "
        "(adjudication_20260717T165139Z.md advisor review): instructions-column evidence "
        "of incomplete ingredient rows. Cured: archive ingredient list is substantially "
        "fuller (13 rows including flour/eggs/bananas/spices vs. the CSV's truncated set)."
    ),
    "imp_9c4f812bcda75ef0": (
        "Crunchy Pretzel Drops No-Bake Cookies -- original finding "
        "(adjudication_20260718T090522Z diet_023 class): instructions stir in undisclosed "
        "cereal, no cereal row. Cured: archive ingredients now include 'puffed corn cereal'."
    ),
    "imp_9e0a542fc2195d5b": (
        "Bananas Baked With Custard -- original finding (adjudication_20260717T165139Z.md "
        "advisor review): instructions-column evidence of incomplete ingredient rows. "
        "Cured: archive ingredients now include bread, egg yolks, milk, sultanas."
    ),
    "imp_9ff0ac08d2b353ca": (
        "Banana Bran Muffins with Strawberry Butter -- original finding "
        "(adjudication_20260717T165139Z.md advisor review): instructions-column evidence "
        "of incomplete ingredient rows. Cured: archive ingredients now include bran, nuts, "
        "egg, banana, yogurt."
    ),
    "imp_e5c662ec002355d6": (
        "Praline Pecan Crunch -- original finding (adjudication_20260718T090522Z diet_023 "
        "class): instructions stir in undisclosed cereal, no cereal row. Cured: archive "
        "ingredients now include 'Quaker Oatmeal Squares Cereal'."
    ),
    "imp_fbfd3dda61af5cd5": (
        "No-Bake Cereal Bars -- original finding (adjudication_20260718T090522Z diet_023 "
        "class): instructions stir in undisclosed cereal, no cereal row. Cured: archive "
        "ingredients now include 'Cheerios toasted oat cereal'."
    ),
    "imp_ffba7239b17c5b29": (
        "Spicy Fish Cakes -- original finding (adjudication_20260717T145539Z injection_014): "
        "instructions 'Cut the fish into small pieces' with no fish ingredient row. Cured: "
        "archive ingredients now include 'fish fillets'."
    ),
}


def _utcnow_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_jsonl_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str))
            handle.write("\n")


def _atomic_copy_file(src: Path, dst: Path) -> None:
    """Copy `src` to `dst` atomically (temp file in dst's directory, then
    `os.replace`) -- same pattern as pipeline._write_quarantine_jsonl /
    scripts/quarantine_flagged_recipes.py's _write_quarantine_atomic. Used
    for the pre-reimport history snapshot: a crash partway through the copy
    must never leave a truncated snapshot file at `dst`."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dst.parent), prefix=f".{dst.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(src.read_bytes() if src.exists() else b"")
        os.replace(tmp_name, dst)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.remove(tmp_name)
        raise


def _unit_coverage(recipes: list[Recipe]) -> tuple[int, int]:
    total = sum(len(recipe.ingredients) for recipe in recipes)
    with_unit = sum(1 for recipe in recipes for ingredient in recipe.ingredients if ingredient.unit is not None)
    return with_unit, total


def _write_manual_release_adjudication(
    path: Path,
    manual_release_rows: list[dict],
    old_quarantine_record_by_id: dict[str, dict],
    new_active_by_id: dict[str, Recipe],
    timestamp: str,
) -> None:
    """Write the per-case manual-quarantine-release adjudication record --
    following the written/per-case/dated/citable-rule convention of
    data/evaluation/adjudication_20260717T145539Z.md. Every row in
    `manual_release_rows` gets a verdict: RELEASE JUSTIFIED (pre-approved in
    `_ADVISOR_APPROVED_MANUAL_RELEASES`, advisor-reviewed
    `_ADVISOR_APPROVAL_DATE`) or NOT PRE-APPROVED (the run-level halt in
    `run_scraped_archive_reimport` stops the corpus/sidecar write whenever
    this second case occurs -- see that function)."""
    lines = [
        "# Manual-quarantine release adjudication",
        "",
        f"- Re-import run: {timestamp} (task A1, scraped-archive re-import).",
        "- Scope: every id in this run's `released` bucket whose PRIOR quarantine "
        "record has `quarantine_reason.check == \"manual_adjudication\"` -- i.e. a "
        "recipe that was never quarantined by the automated title/instructions "
        "integrity scans, but by a human/advisor adjudication of a specific "
        "adversarial-benchmark finding.",
        "- Why this file exists: an automated re-import passing its OWN checks is "
        "not the same evidence as a human re-reviewing the ORIGINAL manual finding. "
        "This file is the written record that a human (the advisor) did exactly "
        "that, per case, for every id below -- consistent with this project's "
        "adjudication convention (data/evaluation/adjudication_20260717T145539Z.md): "
        "verdict, matched defect, served recipe's actual ingredient rows, citable "
        "cure evidence.",
        f"- Adjudicator: advisor, {_ADVISOR_APPROVAL_DATE} (A1 revise round).",
        "",
        "## Cases",
        "",
    ]

    for row in manual_release_rows:
        recipe_id = row["recipe_id"]
        prior_record = old_quarantine_record_by_id.get(recipe_id) or {}
        old_recipe = prior_record.get("recipe") or {}
        new_recipe = new_active_by_id.get(recipe_id)
        old_ingredients = [item.get("name") for item in old_recipe.get("ingredients", [])]
        new_ingredients = [item.name for item in new_recipe.ingredients] if new_recipe else []
        explanation = prior_record.get("quarantine_reason", {}).get("explanation", "(no explanation on file)")

        approved = _ADVISOR_APPROVED_MANUAL_RELEASES.get(recipe_id)

        lines.append(f"### {recipe_id} -- {row['title']!r}")
        lines.append(f"- Foodcom source id: {old_recipe.get('source_url')}")
        lines.append("- Original quarantine check: manual_adjudication")
        lines.append(f"- Original quarantine reason: {explanation}")
        lines.append(f"- Old (CSV-import) ingredient rows: {old_ingredients}")
        lines.append(f"- New (scraped-archive) ingredient rows: {new_ingredients}")
        if approved:
            lines.append(f"- Cure evidence: {approved}")
            lines.append(
                f"- Verdict: RELEASE JUSTIFIED -- defect cured at source, "
                f"advisor-reviewed {_ADVISOR_APPROVAL_DATE}"
            )
        else:
            lines.append(
                "- Cure evidence: NONE ON FILE -- this id is not in "
                "_ADVISOR_APPROVED_MANUAL_RELEASES."
            )
            lines.append(
                "- Verdict: NOT PRE-APPROVED -- manual quarantine decisions may never be "
                "silently overturned by an automated run. This run's HALT (see console "
                "output / run report) stopped the corpus/sidecar write until a human "
                "reviews this specific case and adds it to the allowlist with cited cure "
                "evidence."
            )
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_scraped_archive_reimport(source_dir: str, *, no_reindex: bool = False) -> int:
    """Full re-import + reconciliation of the corpus from the scraped
    Food.com archive against whatever is CURRENTLY on disk. See this
    module's docstring and `docs/` task spec (A1, 2026-07-19) for the full
    contract: id ledger, released/newly-quarantined/unsourced reports,
    allergen before/after diff, unit-coverage stat, and three pre-registered
    halts that stop the run BEFORE any corpus/sidecar file is rewritten.

    Returns a process exit code (0 = wrote the new corpus, 1 = aborted
    before writing anything -- either a halt tripped or the mandatory
    history snapshot could not be taken/verified).
    """
    settings = get_settings()
    output_path = Path(settings.recipe_path).parent / "imported_recipes.jsonl"
    quarantine_path = output_path.parent / "quarantined_recipes.jsonl"
    history_dir = output_path.parent / "quarantine_history"
    timestamp = _utcnow_ts()

    print(f"=== Food.com scraped-archive re-import ({timestamp}) ===")
    print(f"Source archive dir: {source_dir}")
    print(f"Corpus output: {output_path}")
    print(f"Quarantine sidecar: {quarantine_path}")

    # --- Load OLD state before anything is touched. -------------------------
    old_active = load_recipes(output_path)
    old_quarantine_records = _read_jsonl(quarantine_path)
    old_quarantined = [Recipe.model_validate(record["recipe"]) for record in old_quarantine_records]

    old_active_by_id = {recipe.recipe_id: recipe for recipe in old_active}
    old_quarantined_by_id = {recipe.recipe_id: recipe for recipe in old_quarantined}
    old_ids = set(old_active_by_id) | set(old_quarantined_by_id)
    print(
        f"Old corpus: {len(old_active_by_id)} active + {len(old_quarantined_by_id)} quarantined "
        f"= {len(old_ids)} total ids"
    )

    # --- History snapshot of the quarantine sidecar -- REFUSE on failure. ---
    history_path = history_dir / f"quarantined_recipes_pre_scrape_reimport_{timestamp}.jsonl"
    try:
        _atomic_copy_file(quarantine_path, history_path)
        old_bytes = quarantine_path.read_bytes() if quarantine_path.exists() else b""
        if history_path.read_bytes() != old_bytes:
            raise RuntimeError("history snapshot is not byte-identical to the source sidecar")
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure here must abort
        print(
            f"\nABORT: failed to snapshot the existing quarantine sidecar to history before "
            f"proceeding ({exc}). No corpus/sidecar files were touched."
        )
        return 1
    print(f"Snapshotted current quarantine sidecar -> {history_path} (byte-identical, verified)")

    # --- Dry-run the pipeline over the full archive. -------------------------
    # ALL 4,235 archive files go through both integrity checks fresh here --
    # the frontmatter `corpus:` field is provenance/reporting only and is
    # never read by the adapter or the pipeline to skip or pre-decide a
    # check (verified: FoodComScrapedArchiveAdapter.to_candidate never reads
    # `raw["corpus"]` at all).
    adapter = FoodComScrapedArchiveAdapter()
    pipeline = CorpusImportPipeline(adapter)
    report = pipeline.run(
        source_dir, output_path, existing_recipes=[], quarantine_path=quarantine_path, dry_run=True
    )
    print(f"\nArchive dry-run: {report.summary()}")

    new_active = report.recipes
    new_quarantine_records = report.quarantine_records
    new_quarantined = [Recipe.model_validate(record["recipe"]) for record in new_quarantine_records]
    new_active_by_id = {recipe.recipe_id: recipe for recipe in new_active}
    new_quarantined_by_id = {recipe.recipe_id: recipe for recipe in new_quarantined}
    new_quarantine_record_by_id = {record["recipe"]["recipe_id"]: record for record in new_quarantine_records}
    old_quarantine_record_by_id = {record["recipe"]["recipe_id"]: record for record in old_quarantine_records}

    def _foodcom_ids_from_candidate_ids(candidate_ids: list[str]) -> set[str]:
        return {
            candidate_id[len(_SCRAPED_CANDIDATE_ID_PREFIX):]
            for candidate_id in candidate_ids
            if candidate_id.startswith(_SCRAPED_CANDIDATE_ID_PREFIX)
        }

    adapter_rejected_foodcom_ids = set(report.rejected_by_adapter_source_ids)
    failed_validation_foodcom_ids = _foodcom_ids_from_candidate_ids(report.failed_validation_candidate_ids)
    duplicate_foodcom_ids = _foodcom_ids_from_candidate_ids(report.duplicate_candidate_ids)

    archived_foodcom_ids = {path.stem for path in Path(source_dir).glob("*.md")}
    print(f"Archive files present: {len(archived_foodcom_ids)}")

    # --- Build the per-id reconciliation ledger. -----------------------------
    bucket_names = [
        "still_active",
        "still_quarantined",
        "released",
        "newly_quarantined_previously_active",
        "duplicate",
        "validation_failed",
        "unsourced",
        "adapter_rejected",
    ]
    buckets: dict[str, list[dict]] = {name: [] for name in bucket_names}
    unclassified: list[dict] = []

    for recipe_id in sorted(old_ids):
        old_recipe = old_active_by_id.get(recipe_id) or old_quarantined_by_id.get(recipe_id)
        was_active = recipe_id in old_active_by_id
        foodcom_id = old_recipe.source_url if old_recipe else None
        row = {
            "recipe_id": recipe_id,
            "foodcom_id": foodcom_id,
            "title": old_recipe.title if old_recipe else None,
            "was_active_before": was_active,
        }

        if not foodcom_id or foodcom_id not in archived_foodcom_ids:
            buckets["unsourced"].append(row)
        elif foodcom_id in adapter_rejected_foodcom_ids:
            buckets["adapter_rejected"].append(row)
        elif foodcom_id in failed_validation_foodcom_ids:
            buckets["validation_failed"].append(row)
        elif foodcom_id in duplicate_foodcom_ids:
            buckets["duplicate"].append(row)
        elif recipe_id in new_active_by_id:
            buckets["released" if not was_active else "still_active"].append(row)
        elif recipe_id in new_quarantined_by_id:
            buckets["newly_quarantined_previously_active" if was_active else "still_quarantined"].append(row)
        else:
            unclassified.append(row)

    if unclassified:
        print(
            f"\n** WARNING: {len(unclassified)} old ids could not be classified into any "
            f"bucket -- see the ledger file for details. **"
        )

    new_only_ids = sorted(
        recipe.recipe_id for recipe in (new_active + new_quarantined) if recipe.recipe_id not in old_ids
    )
    if new_only_ids:
        print(
            f"\n** NOTE: {len(new_only_ids)} ids in this run's output were not present in the "
            f"old corpus at all: {new_only_ids[:20]} **"
        )

    bucket_counts = {name: len(rows) for name, rows in buckets.items()}
    total_bucketed = sum(bucket_counts.values()) + len(unclassified)
    print("\n--- Id ledger bucket counts ---")
    for name in bucket_names:
        print(f"  {name}: {bucket_counts[name]}")
    if unclassified:
        print(f"  unclassified: {len(unclassified)}")
    print(
        f"  TOTAL bucketed: {total_bucketed} (old ids: {len(old_ids)}, "
        f"new-only survivors: {len(new_only_ids)})"
    )
    if total_bucketed != len(old_ids):
        print(
            f"  ** WARNING: bucketed total {total_bucketed} != old id count {len(old_ids)} "
            "-- reconciliation does not add up, investigate before trusting this run. **"
        )

    ledger_path = output_path.parent / f"scraped_archive_reimport_ledger_{timestamp}.jsonl"
    ledger_rows = [{"bucket": name, **row} for name, rows in buckets.items() for row in rows]
    ledger_rows += [{"bucket": "unclassified", **row} for row in unclassified]
    ledger_rows += [
        {"bucket": "new_only_survivor", "recipe_id": recipe_id, "foodcom_id": None, "title": None}
        for recipe_id in new_only_ids
    ]
    _write_jsonl_records(ledger_path, ledger_rows)
    print(f"Wrote id ledger -> {ledger_path}")

    # --- Released records. ----------------------------------------------------
    released_path = history_dir / f"released_{timestamp}.jsonl"
    released_records = []
    for row in buckets["released"]:
        recipe = new_active_by_id[row["recipe_id"]]
        prior_record = old_quarantine_record_by_id.get(row["recipe_id"])
        released_records.append(
            {
                "recipe_id": row["recipe_id"],
                "title": recipe.title,
                "prior_check": (prior_record or {}).get("quarantine_reason", {}).get("check"),
                "released_because": (
                    "passed title+instructions integrity on scraped original-page text "
                    "(scraper_version=1)"
                ),
                "released_at_utc": timestamp,
            }
        )
    _write_jsonl_records(released_path, released_records)
    old_quarantined_count = len(old_quarantined_by_id)
    released_pct = 100 * len(released_records) / max(old_quarantined_count, 1)
    print(
        f"\nReleased (previously quarantined, now passes both checks): {len(released_records)} "
        f"of {old_quarantined_count} old quarantined ({released_pct:.2f}%) -> {released_path}"
    )
    print(
        "  released% is a NON-GATING report figure for this source upgrade only -- see the "
        "advisor adjudication of 2026-07-19 (811/982 have the flagged term literally present "
        "in the scraped rows, 159/982 pass a fresh recheck via category vocabulary, "
        f"{len(_ADVISOR_APPROVED_MANUAL_RELEASES)}/982 are pre-existing manual-adjudication "
        "quarantines individually examined and cured at source -- see "
        "manual_release_adjudication_<ts>.md below)."
    )

    # --- Manual-quarantine-release handling (structural rule, 2026-07-19 revise) ---
    # A released id whose PRIOR quarantine record was a human/advisor
    # `manual_adjudication` (never produced by the automated scans) may
    # NEVER be silently released by an automated run. This run always
    # emits the full per-case adjudication record when such a release
    # would occur; if writing it fails, or if any such id is not on the
    # advisor-reviewed allowlist, the run halts BEFORE the corpus/sidecar
    # write (checked together with the other halts below).
    manual_release_rows = [
        row
        for row in buckets["released"]
        if (old_quarantine_record_by_id.get(row["recipe_id"]) or {}).get("quarantine_reason", {}).get("check")
        == "manual_adjudication"
    ]
    unapproved_manual_releases = [
        row for row in manual_release_rows if row["recipe_id"] not in _ADVISOR_APPROVED_MANUAL_RELEASES
    ]
    manual_adjudication_path = history_dir / f"manual_release_adjudication_{timestamp}.md"
    if manual_release_rows:
        try:
            _write_manual_release_adjudication(
                manual_adjudication_path,
                manual_release_rows,
                old_quarantine_record_by_id,
                new_active_by_id,
                timestamp,
            )
        except Exception as exc:  # noqa: BLE001 -- any failure here must abort
            print(
                f"\nABORT: failed to write the manual-release adjudication record ({exc}). "
                "No corpus/sidecar files were touched."
            )
            return 1
        print(
            f"\nManual-quarantine releases: {len(manual_release_rows)} "
            f"({len(manual_release_rows) - len(unapproved_manual_releases)} advisor-approved, "
            f"{len(unapproved_manual_releases)} NOT pre-approved) -> {manual_adjudication_path}"
        )
        if unapproved_manual_releases:
            print(
                f"  ** {len(unapproved_manual_releases)} unapproved: "
                f"{[row['recipe_id'] for row in unapproved_manual_releases]} **"
            )
    else:
        print("\nManual-quarantine releases: 0 (nothing to adjudicate this run).")

    # --- Newly-quarantined-previously-active report. ---------------------------
    newly_quarantined_rows = buckets["newly_quarantined_previously_active"]
    per_check_counts: Counter = Counter()
    newly_quarantined_records = []
    for row in newly_quarantined_rows:
        record = new_quarantine_record_by_id.get(row["recipe_id"])
        check = (record or {}).get("quarantine_reason", {}).get("check", "unknown")
        per_check_counts[check] += 1
        newly_quarantined_records.append({"recipe_id": row["recipe_id"], "title": row["title"], "check": check})
    newly_quarantined_path = history_dir / f"newly_quarantined_previously_active_{timestamp}.jsonl"
    _write_jsonl_records(newly_quarantined_path, newly_quarantined_records)
    old_active_count = len(old_active_by_id)
    newly_quarantined_pct = 100 * len(newly_quarantined_rows) / max(old_active_count, 1)
    print(
        f"\nNewly quarantined (previously active): {len(newly_quarantined_rows)} of "
        f"{old_active_count} old active ({newly_quarantined_pct:.2f}%)"
    )
    print(f"  per-check breakdown: {dict(per_check_counts)}")
    print(f"  examples (up to 20): {[record['title'] for record in newly_quarantined_records[:20]]}")
    print(f"  full id list -> {newly_quarantined_path}")

    # --- Unsourced file (the known-dead ids). ----------------------------------
    unsourced_path = history_dir / f"unsourced_recipes_{timestamp}.jsonl"
    unsourced_records = []
    for row in buckets["unsourced"]:
        recipe_id = row["recipe_id"]
        if recipe_id in old_active_by_id:
            old_full = old_active_by_id[recipe_id].model_dump(mode="json")
        else:
            record = old_quarantine_record_by_id.get(recipe_id)
            old_full = record["recipe"] if record else None
        unsourced_records.append(
            {
                "recipe_id": recipe_id,
                "old_record": old_full,
                "reason": (
                    "original page unreachable (HTTP 500 on all attempts); excluded from "
                    "scraped-archive re-import"
                ),
            }
        )
    _write_jsonl_records(unsourced_path, unsourced_records)
    print(f"\nUnsourced (no archive file, removed from active corpus): {len(unsourced_records)} -> {unsourced_path}")
    for row in buckets["unsourced"]:
        print(f"  {row['recipe_id']} ({row['title']!r})")

    # --- Allergen before/after diff report. -------------------------------------
    allergen_diff_path = output_path.parent / f"allergen_diff_report_{timestamp}.jsonl"
    allergen_diff_rows = []
    loss_rows = []
    gain_count = 0
    considered_ids = sorted((set(new_active_by_id) | set(new_quarantined_by_id)) & old_ids)
    for recipe_id in considered_ids:
        old_recipe = old_active_by_id.get(recipe_id) or old_quarantined_by_id.get(recipe_id)
        new_recipe = new_active_by_id.get(recipe_id) or new_quarantined_by_id.get(recipe_id)
        old_allergens = set(old_recipe.allergens)
        new_allergens = set(new_recipe.allergens)
        if old_allergens == new_allergens and len(old_recipe.ingredients) == len(new_recipe.ingredients):
            continue
        lost = sorted(old_allergens - new_allergens)
        gained = sorted(new_allergens - old_allergens)
        row = {
            "recipe_id": recipe_id,
            "title": new_recipe.title,
            "old_allergens": sorted(old_allergens),
            "new_allergens": sorted(new_allergens),
            "lost_labels": lost,
            "gained_labels": gained,
            "old_ingredient_count": len(old_recipe.ingredients),
            "new_ingredient_count": len(new_recipe.ingredients),
        }
        allergen_diff_rows.append(row)
        if lost:
            loss_rows.append(row)
        if gained:
            gain_count += 1
    _write_jsonl_records(allergen_diff_path, allergen_diff_rows)

    loss_pct = 100 * len(loss_rows) / max(len(considered_ids), 1)
    total_lost_label_pairs = sum(len(row["lost_labels"]) for row in loss_rows)
    print(
        f"\nAllergen diff: {len(allergen_diff_rows)} recipes changed allergens/ingredient-count "
        f"(of {len(considered_ids)} considered). {len(loss_rows)} recipes LOST >=1 allergen label "
        f"({loss_pct:.2f}%, {total_lost_label_pairs} individual (recipe, label) pairs, REPORTED "
        f"only -- see the serve-time coverage gate below); {gain_count} recipes gained >=1 label."
    )
    print(f"  full diff -> {allergen_diff_path}")
    if loss_rows:
        print("  LOSS examples (up to 20):")
        for row in loss_rows[:20]:
            print(f"    {row['recipe_id']} {row['title']!r}: lost {row['lost_labels']}")

    # --- Serve-time coverage check (the ACTUAL hard gate, 2026-07-19 revise). --
    # Not "did the derived `allergens` metadata label change" (measured
    # above, reported only) but "is the safety-relevant ingredient still
    # detectable by the mechanism that actually decides what gets served" --
    # app.graph.nodes -> constraint_engine.validate_recipe ->
    # contains_allergen, which substring-matches ingredient NAMES directly
    # and is independent of the (less robust, exact-match) `allergens`
    # metadata field. For every individually lost label L on recipe R,
    # contains_allergen(new_recipe_R, [L]) must still be True. ANY False is
    # a genuine live safety gap and halts the run.
    serve_time_gaps = []
    for row in loss_rows:
        new_recipe = new_active_by_id.get(row["recipe_id"]) or new_quarantined_by_id.get(row["recipe_id"])
        for label in row["lost_labels"]:
            if not contains_allergen(new_recipe, [label]):
                serve_time_gaps.append({"recipe_id": row["recipe_id"], "title": row["title"], "label": label})
    serve_time_gaps_path = output_path.parent / f"serve_time_coverage_gaps_{timestamp}.jsonl"
    _write_jsonl_records(serve_time_gaps_path, serve_time_gaps)
    print(
        f"\nServe-time coverage check: {len(serve_time_gaps)}/{total_lost_label_pairs} lost "
        f"(recipe, label) pairs are ALSO undetectable by contains_allergen (the live safety "
        f"gate) -> {serve_time_gaps_path}"
    )
    if serve_time_gaps:
        print("  GAP examples (up to 20):")
        for gap in serve_time_gaps[:20]:
            print(f"    {gap['recipe_id']} {gap['title']!r}: label {gap['label']!r}")

    # --- Unit-coverage stat. ------------------------------------------------
    old_with_unit, old_total = _unit_coverage(old_active + old_quarantined)
    new_with_unit, new_total = _unit_coverage(new_active + new_quarantined)
    old_unit_pct = 100 * old_with_unit / max(old_total, 1)
    new_unit_pct = 100 * new_with_unit / max(new_total, 1)
    print(
        f"\nUnit coverage: before {old_with_unit}/{old_total} ({old_unit_pct:.2f}%) -> "
        f"after {new_with_unit}/{new_total} ({new_unit_pct:.2f}%)"
    )

    # --- HALTS (stop BEFORE writing anything). Redefined 2026-07-19 by ---------
    # advisor REVISE verdict after investigating the first run's trip of the
    # original label-diff-%/released-% gates -- see the module-level comment
    # above `_ALLERGEN_LOSS_HALT_FRACTION` for the full rationale.
    halted = False

    # (a) NEW hard gate: serve-time coverage. Any gap is a genuine live
    # safety regression (not a metadata artifact) and blocks the release.
    if serve_time_gaps:
        print(
            f"\n** HALT: {len(serve_time_gaps)} serve-time coverage gap(s) -- a lost allergen "
            "label is undetectable by contains_allergen (the live safety gate) on the recipe "
            "that would actually be served. This is a release blocker, not a metadata issue. **"
        )
        halted = True

    # (b) Raw label-diff percentage: REPORTED above, never gates (retired).
    # (c) released%: REPORTED above, non-gating for THIS source upgrade only
    # (advisor adjudication 2026-07-19 -- see the note printed with the
    # released-records report above). Never gates here.

    # (d) Unchanged hard gate.
    if len(newly_quarantined_rows) > _NEWLY_QUARANTINED_HALT_FRACTION * old_active_count:
        print(
            f"\n** HALT: newly-quarantined-previously-active {newly_quarantined_pct:.2f}% "
            f"exceeds the {_NEWLY_QUARANTINED_HALT_FRACTION:.0%} pre-registered threshold. **"
        )
        halted = True

    # Structural rule (item 3, 2026-07-19 revise): any manual_adjudication
    # release not on the advisor-reviewed allowlist halts, regardless of
    # the other gates -- manual quarantine decisions may never be silently
    # overturned by an automated run.
    if unapproved_manual_releases:
        print(
            f"\n** HALT: {len(unapproved_manual_releases)} manual_adjudication-quarantined "
            "id(s) would be released WITHOUT advisor pre-approval -- see "
            f"{manual_adjudication_path}. **"
        )
        halted = True

    if halted:
        print(
            "\n*** HALT TRIPPED -- STOPPING BEFORE WRITING THE CORPUS/SIDECAR. ***\n"
            "*** imported_recipes.jsonl and quarantined_recipes.jsonl are UNCHANGED. ***\n"
            "*** All reconciliation artifacts above were still written for review. ***"
        )
        return 1

    # --- Write the corpus + sidecar for real. --------------------------------
    pipeline.write(output_path, quarantine_path, report)
    print(f"\nWrote {len(new_active)} active recipes -> {output_path}")
    print(f"Wrote {len(new_quarantine_records)} quarantined recipes -> {quarantine_path}")

    if not no_reindex:
        indexed = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=True)
        print(f"\nRebuilt vector store (clean): {indexed} recipes indexed.")
        print(f"Active corpus line count: {len(new_active)} | embedded count: {indexed}")

    print("\n=== Re-import complete. ===")
    return 0


def _run_generic_import(args: argparse.Namespace) -> int:
    settings = get_settings()
    output_path = Path(settings.recipe_path).parent / "imported_recipes.jsonl"

    adapter = _ADAPTERS[args.dataset]()
    pipeline = CorpusImportPipeline(adapter)
    report = pipeline.run(args.source, output_path, limit=args.limit)

    print(f"Corpus import ({args.dataset}): {report.summary()}")
    print(f"Wrote {report.survivors} recipes to {output_path}")

    if report.read:
        pct_with_drop = 100 * report.recipes_with_narrative_steps_dropped / report.read
        pct_below_min = 100 * report.recipes_below_min_instructions_after_cleaning / report.read
        pct_caused_by_cleaning = 100 * report.recipes_rejected_because_of_cleaning / report.read
        print(
            f"\nInstruction cleaning: {pct_with_drop:.2f}% of read recipes had >=1 "
            f"narrative step dropped.\n"
            f"{pct_below_min:.2f}% ended up below the 2-instruction minimum and were "
            f"rejected (this includes recipes that only ever had <2 raw steps -- "
            f"always going to be rejected regardless of cleaning).\n"
            f"Of those, {pct_caused_by_cleaning:.2f}% are attributable to cleaning "
            f"itself (had >=2 raw steps, but dropping narrative ones pushed them "
            f"below 2) -- this is the false-positive-collateral number to eyeball."
        )
        if pct_caused_by_cleaning > 5:
            print(
                f"** FLAG: cleaning-caused rejection rate {pct_caused_by_cleaning:.2f}% "
                f"exceeds the 5% threshold. **"
            )

    # Title/ingredient integrity (app.services.corpus_import.
    # title_ingredient_integrity): recipes whose own title names an allergen
    # absent from both their ingredients and derived allergens are already
    # quarantined by the pipeline (never written to output_path) -- this is
    # just visibility into how often that happened for THIS import run. A
    # 1% threshold (lower than the 5% cleaning-collateral threshold above)
    # because this is a safety-relevant metric, not a cosmetic one: the
    # 2026-07 finding this check exists to prevent measured at ~4.2% of the
    # historical Food.com corpus, so anything above 1% here is worth a human
    # actually reading the quarantine sidecar before trusting this import.
    considered = report.survivors + report.title_ingredient_mismatches_flagged
    if considered:
        pct_quarantined = 100 * report.title_ingredient_mismatches_flagged / considered
        print(
            f"\nTitle/ingredient integrity: {report.title_ingredient_mismatches_flagged} recipes "
            f"({pct_quarantined:.2f}% of {considered} that reached recipe construction) were "
            f"quarantined -- their own title names an allergen absent from both their "
            f"ingredients and derived allergens field. See the quarantine sidecar "
            f"(default: imported_recipes.jsonl's sibling quarantined_recipes.jsonl)."
        )
        if pct_quarantined > 1:
            print(
                f"** FLAG: title/ingredient integrity quarantine rate {pct_quarantined:.2f}% "
                f"exceeds the 1% threshold -- review the quarantine sidecar before trusting "
                f"this import. **"
            )

    examples = getattr(adapter, "example_dropped_below_min", [])
    if examples:
        print(f"\nExample recipes rejected BECAUSE OF cleaning ({len(examples)} shown):")
        for example in examples:
            print(f"\n--- {example['title']} ---")
            print("Original steps:")
            for step in example["original_instructions"]:
                print(f"  - {step}")
            print(f"Cleaned steps (survivors): {example['cleaned_instructions'] or '(none)'}")

    if report.example_title_ingredient_mismatches:
        print(
            f"\nExample recipes quarantined for title/ingredient integrity "
            f"({len(report.example_title_ingredient_mismatches)} shown):"
        )
        for example in report.example_title_ingredient_mismatches:
            print(f"  - {example['title']!r} ({example['recipe_id']}) -- categories: {example['categories']}")

    if not args.no_reindex:
        indexed = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=True)
        print(f"\nRebuilt vector store (clean): {indexed} recipes indexed.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=sorted(_ADAPTERS), required=True)
    parser.add_argument(
        "--source", required=True, help="Path to the downloaded dataset file, or (for "
        "foodcom_scraped_archive) the archive directory (data/scraped/foodcom)"
    )
    parser.add_argument("--limit", type=int, default=5000, help="Ignored by foodcom_scraped_archive")
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="Skip rebuilding the vector store after writing the corpus file",
    )
    args = parser.parse_args()

    if args.dataset == "foodcom_scraped_archive":
        return run_scraped_archive_reimport(args.source, no_reindex=args.no_reindex)
    return _run_generic_import(args)


if __name__ == "__main__":
    raise SystemExit(main())
