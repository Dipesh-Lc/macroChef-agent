"""One-off, idempotent, re-runnable enrichment pass: apply LLM-classified
`cuisine`/`meal_type` values from `data/processed/llm_tag_inferences.jsonl`
onto `data/processed/imported_recipes.jsonl` and
`data/processed/sample_recipes.jsonl`.

Background: deterministic tag-mining (`resolve_cuisine`/`resolve_meal_type`,
plus the gazetteer/dish-name backfill) structurally cannot reach several
major true classes -- American/Italian/French/Mediterranean cuisines are
never self-tagged by Food.com users as literal tags, and "dinner"/"snack"
never appear as literal tags either. `llm_tag_inferences.jsonl` is the
output of a batch, human-supervised LLM classification pass (title +
ingredient names ONLY -- never allergy/nutrition-relevant fields) run over
every recipe deterministic mining left as `cuisine_source`/`meal_type_source
== "unknown"`, biased hard toward abstaining (omitting the key) whenever the
signal wasn't genuinely clear. This is display-only enrichment: the LLM
never decides an allergy or nutrition outcome, and this script never touches
`ingredients`, `allergens`, `diet_tags`, or any nutrition field.

Safety rule (deliberately MORE conservative than "only overwrite `unknown`"):
this script applies an inferred value to a field ONLY if that field is
currently empty/`None` on the record -- regardless of what `cuisine_source`/
`meal_type_source` says. This matters for `sample_recipes.jsonl`: its 25
seed recipes have `cuisine_source`/`meal_type_source == None` (never
stamped) but most already have a correct, curator-set `cuisine`/`meal_type`
value. Gating on the source label alone would have let the LLM pass
silently overwrite at least one already-correct value (`r_009`, curator set
`cuisine="Mexican"`; the independent LLM classification pass on the same
title+ingredients produced `"Tex-Mex"` instead) with a plausible-but-wrong
one. Gating on "is the field currently empty" instead makes that class of
regression structurally impossible: a value can only be written into a
field that had nothing in it before.

Only recipes actually assigned a value (by this run) get
`cuisine_source="llm_inferred"` / `meal_type_source="llm_inferred"` stamped;
untouched fields keep whatever source label they already had.

Usage:
    python scripts/apply_llm_tag_inferences.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL_CUISINES = {
    "American", "Austrian", "Belgian", "British", "Cajun", "Caribbean", "Chinese",
    "Creole", "Cuban", "Czech", "Dutch", "Ethiopian", "Filipino", "Finnish", "French",
    "German", "Greek", "Hungarian", "Indian", "Indonesian", "Italian", "Japanese",
    "Korean", "Lebanese", "Mediterranean", "Mexican", "Middle Eastern", "Moroccan",
    "Nepali", "Norwegian", "Persian", "Peruvian", "Polish", "Portuguese", "Russian",
    "Spanish", "Swedish", "Swiss", "Tex-Mex", "Thai", "Turkish", "Vietnamese",
}
CANONICAL_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack", "dessert"}

INFERENCES_PATH = ROOT / "data" / "processed" / "llm_tag_inferences.jsonl"
CORPUS_PATHS = [
    ROOT / "data" / "processed" / "imported_recipes.jsonl",
    ROOT / "data" / "processed" / "sample_recipes.jsonl",
]


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_jsonl_atomic(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _load_inferences() -> dict[str, dict]:
    """Loads llm_tag_inferences.jsonl into recipe_id -> {cuisine?, meal_type?},
    silently dropping (with a warning) any entry whose value isn't in the
    canonical taxonomy -- defense in depth on top of the per-batch validator
    already run during classification."""
    raw = _read_jsonl(INFERENCES_PATH)
    by_id: dict[str, dict] = {}
    dropped = 0
    for entry in raw:
        recipe_id = entry.get("recipe_id")
        if not recipe_id:
            continue
        cuisine = entry.get("cuisine")
        meal_type = entry.get("meal_type")
        if cuisine is not None and cuisine not in CANONICAL_CUISINES:
            print(f"  WARNING: dropping non-canonical cuisine {cuisine!r} for {recipe_id}")
            cuisine = None
            dropped += 1
        if meal_type is not None and meal_type not in CANONICAL_MEAL_TYPES:
            print(f"  WARNING: dropping non-canonical meal_type {meal_type!r} for {recipe_id}")
            meal_type = None
            dropped += 1
        if recipe_id in by_id:
            print(f"  WARNING: duplicate recipe_id {recipe_id!r} in inferences file; keeping last")
        by_id[recipe_id] = {"cuisine": cuisine, "meal_type": meal_type}
    print(f"Loaded {len(raw)} inference lines ({len(by_id)} unique recipe_ids, {dropped} values dropped).")
    return by_id


def _apply_to_corpus(path: Path, inferences: dict[str, dict], dry_run: bool) -> dict:
    if not path.exists():
        print(f"  (skipping -- file does not exist: {path})")
        return {}

    records = _read_jsonl(path)
    before_cuisine_nonnull = sum(1 for r in records if r.get("cuisine"))
    before_meal_type_nonnull = sum(1 for r in records if r.get("meal_type"))
    before_cuisine_source: Counter = Counter(r.get("cuisine_source") for r in records)
    before_meal_type_source: Counter = Counter(r.get("meal_type_source") for r in records)

    cuisine_applied = 0
    meal_type_applied = 0
    cuisine_skipped_already_set = 0
    meal_type_skipped_already_set = 0

    for record in records:
        recipe_id = record.get("recipe_id")
        inference = inferences.get(recipe_id)
        if inference is None:
            continue

        if inference.get("cuisine") is not None:
            if not record.get("cuisine"):
                record["cuisine"] = inference["cuisine"]
                record["cuisine_source"] = "llm_inferred"
                cuisine_applied += 1
            else:
                cuisine_skipped_already_set += 1

        if inference.get("meal_type") is not None:
            if not record.get("meal_type"):
                record["meal_type"] = inference["meal_type"]
                record["meal_type_source"] = "llm_inferred"
                meal_type_applied += 1
            else:
                meal_type_skipped_already_set += 1

    after_cuisine_nonnull = sum(1 for r in records if r.get("cuisine"))
    after_meal_type_nonnull = sum(1 for r in records if r.get("meal_type"))
    after_cuisine_source: Counter = Counter(r.get("cuisine_source") for r in records)
    after_meal_type_source: Counter = Counter(r.get("meal_type_source") for r in records)
    total = len(records)

    print(f"\n=== {path.name} ({total} records) ===")
    print(f"  cuisine applied:   {cuisine_applied} (skipped, already set: {cuisine_skipped_already_set})")
    print(f"  meal_type applied: {meal_type_applied} (skipped, already set: {meal_type_skipped_already_set})")
    print(
        f"  cuisine non-null:   {before_cuisine_nonnull}/{total} ({100 * before_cuisine_nonnull / total:.2f}%)"
        f" -> {after_cuisine_nonnull}/{total} ({100 * after_cuisine_nonnull / total:.2f}%)"
    )
    print(
        f"  meal_type non-null: {before_meal_type_nonnull}/{total} ({100 * before_meal_type_nonnull / total:.2f}%)"
        f" -> {after_meal_type_nonnull}/{total} ({100 * after_meal_type_nonnull / total:.2f}%)"
    )
    print(f"  cuisine_source before:   {dict(before_cuisine_source)}")
    print(f"  cuisine_source after:    {dict(after_cuisine_source)}")
    print(f"  meal_type_source before: {dict(before_meal_type_source)}")
    print(f"  meal_type_source after:  {dict(after_meal_type_source)}")

    if not dry_run:
        records.sort(key=lambda r: r["recipe_id"])
        _write_jsonl_atomic(path, records)
        print(f"  Wrote {total} records -> {path}")

    return {
        "cuisine_applied": cuisine_applied,
        "meal_type_applied": meal_type_applied,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report stats; write nothing.")
    args = parser.parse_args()

    print(f"Inferences file: {INFERENCES_PATH}")
    inferences = _load_inferences()

    totals = {"cuisine_applied": 0, "meal_type_applied": 0}
    for path in CORPUS_PATHS:
        result = _apply_to_corpus(path, inferences, args.dry_run)
        for key in totals:
            totals[key] += result.get(key, 0)

    print("\n--- Totals across both corpus files ---")
    print(f"  cuisine values applied:   {totals['cuisine_applied']}")
    print(f"  meal_type values applied: {totals['meal_type_applied']}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
