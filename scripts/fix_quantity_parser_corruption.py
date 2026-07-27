"""One-off, targeted, re-runnable data fix: re-derive `ingredients[].name`/
`amount`/`unit` for the specific corpus rows corrupted by the two
`app/utils/quantity_parser.py` bugs fixed alongside this script (2026-07-27):

  Bug 1 -- fraction-range regex gap: `_LEADING_AMOUNT`'s numeric-range branch
  only accepted decimal operands ("2-4"), not fractions ("2/3-3/4"), so a
  line like "2/3-3/4 cup brown sugar, packed" mis-parsed as amount=0.667
  (just "2/3"), name="-3/4 cup brown sugar, packed" (the corrupted
  remainder). Corruption signature: `name` starts with "-" immediately
  followed by a digit.

  Bug 2 -- container-word name pollution: a container word ("can",
  "package", "jar", "box", "bag", "bottle", "container", singular/plural)
  with NO preceding parenthetical size was never recognized as a unit, so it
  leaked into `name` (e.g. "1 can black beans..." -> name="can black
  beans...", unit=None). Corruption signature: `name` starts with one of
  those words AND `unit` is None.

  Bug 3 -- pack-size parenthetical fraction gap + unit-vocabulary expansion
  (added in this script's second pass, same day): `_PACK_SIZE_RE`'s
  parenthetical-size group only accepted a plain decimal, so a line like
  "1 (10 3/4 ounce) can condensed cream of asparagus soup" failed the whole
  pack-size match and the container word leaked into `name` anyway (same
  degradation as bug 2, just gated behind a fraction in the parenthetical).
  Separately, "pinch"/"dash"/"stalk"/"head"/"bunch" (singular and plural)
  were not yet recognized count units, so they leaked into `name` the same
  way container words used to. Both sub-cases share bug 2's exact repair
  mechanism (see below) and are handled by ONE generic pass in this script:
  any ingredient with `unit is None` and a non-null `amount` is reparsed via
  "{amount} {name}" through the now-further-fixed `parse_quantity_string`;
  if that newly resolves a unit, the row is fixed. This generic pass
  subsumes what a bug-3-specific signature regex would have caught, without
  needing to enumerate every new vocabulary word's own signature.

This is deliberately a TARGETED fix, not a full corpus reparse from raw
source text:

  - Bug-2 and bug-3 rows can be safely and fully repaired WITHOUT touching
    the scraped archive at all: neither bug corrupted `amount` (only the
    unit/name split), so reconstructing "{amount} {name}" from the CURRENT
    (corrupted) fields byte-for-byte reproduces the original raw ingredient
    line, and re-running it through the fixed `parse_quantity_string`
    correctly recognizes the unit this time. The bug-3/vocab-expansion pass
    added in this script's second run preserves the original `amount` value
    verbatim (rather than taking the reparsed amount) to avoid any
    float-formatting precision drift on fractional amounts; this differs
    slightly from the earlier bug-2 pass's amount handling, but is
    immaterial in practice since neither bug ever touched `amount`.
  - Bug-1 rows genuinely lost information in the original (buggy) parse --
    `amount` itself was wrong -- so these DO require the original raw
    ingredient text, fetched from each recipe's own scraped-archive source
    file (mirrors `scripts/backfill_cuisine_meal_type_tags.py`'s
    multi-directory verified-lookup pattern; see that script's module
    docstring for why a single-directory reimport is NOT sufficient for
    this corpus).

Every OTHER ingredient row -- including rows on a recipe that has >=1
corrupted row -- is left completely untouched, even though a full
raw-text reparse might occasionally differ by a trivial whitespace nuance:
minimizing blast radius to exactly the rows proven corrupted is the point of
this script. All other Recipe fields (recipe_id, cuisine, meal_type,
cuisine_source, meal_type_source, allergens, instructions, ...) are also
left completely untouched -- this script only ever rewrites the 2 fields
name/unit (bug-2/bug-3 rows) or all 3 of name/amount/unit (bug-1 rows,
which need a real amount fix) on specific ingredient dicts.

Usage:
    python scripts/fix_quantity_parser_corruption.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.corpus_import.adapters import (  # noqa: E402
    ScrapedArchiveIntegrityError,
    _clean_scraped_ingredient,
    _extract_jsonld_block,
    _parse_scraped_frontmatter,
)
from app.utils.quantity_parser import parse_quantity_string  # noqa: E402

# Same fixed priority order as scripts/backfill_cuisine_meal_type_tags.py --
# the 9,986-recipe corpus was assembled from all five scrape batches, not
# just the original `foodcom` migration directory.
_ARCHIVE_DIRS_PRIORITY = [
    "data/scraped/foodcom",
    "data/scraped/foodcom_candidates",
    "data/scraped/foodcom_candidates_ext",
    "data/scraped/foodcom_candidates_ext2",
    "data/scraped/foodcom_candidates_ext3",
]

_CONTAINER_WORDS = (
    "package", "packages", "pkg",
    "can", "cans",
    "jar", "jars",
    "box", "boxes",
    "bag", "bags",
    "bottle", "bottles",
    "container", "containers",
)
_BUG1_SIGNATURE_RE = re.compile(r"^-\d")
_BUG2_SIGNATURE_RE = re.compile(r"^(" + "|".join(_CONTAINER_WORDS) + r")\b", re.I)


def _is_bug1_row(ingredient: dict) -> bool:
    return bool(_BUG1_SIGNATURE_RE.match(ingredient["name"]))


def _is_bug2_row(ingredient: dict) -> bool:
    return ingredient.get("unit") is None and bool(_BUG2_SIGNATURE_RE.match(ingredient["name"]))


# --- Archive lookup (bug-1 rows only) -- same pattern as
# scripts/backfill_cuisine_meal_type_tags.py's _build_stem_index /
# _find_verified_source, duplicated here (not imported) because that script
# is a one-off entry point, not a shared library module. ------------------


def _build_stem_index(dirs: list[str]) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for directory in dirs:
        path = Path(directory)
        if not path.exists():
            print(f"WARNING: archive directory missing: {path}")
            continue
        for file_path in path.glob("*.md"):
            index.setdefault(file_path.stem, []).append(file_path)
    return index


def _find_verified_source(candidate_paths: list[Path], expected_recipe_id: str) -> tuple[dict | None, str | None]:
    if not candidate_paths:
        return None, "no_candidate_files"

    last_reason = "no_candidate_files"
    for path in candidate_paths:
        try:
            text = path.read_text(encoding="utf-8")
            frontmatter = _parse_scraped_frontmatter(text, path)
        except ScrapedArchiveIntegrityError:
            last_reason = "unparseable_frontmatter"
            continue
        if frontmatter.get("http_status") != "200":
            last_reason = "non_200_http_status"
            continue
        if frontmatter.get("recipe_id") != expected_recipe_id:
            last_reason = "recipe_id_mismatch"
            continue
        try:
            jsonld = _extract_jsonld_block(text, path)
        except ScrapedArchiveIntegrityError:
            last_reason = "unparseable_jsonld"
            continue
        return jsonld, None
    return None, last_reason


def _reparsed_raw_ingredients(jsonld: dict) -> list[dict]:
    """Re-derive {name, amount, unit} for every ingredient line in a
    recipe's raw JSON-LD, via the exact same cleaning
    (`_clean_scraped_ingredient`) and parsing (`parse_quantity_string`,
    now fixed) `FoodComScrapedArchiveAdapter.to_candidate` applies at
    import time, filtering out any resulting empty name exactly like
    `Recipe._drop_empty_ingredients` does."""
    raw_ingredients = jsonld.get("recipeIngredient")
    if not isinstance(raw_ingredients, list):
        return []
    texts = [_clean_scraped_ingredient(item) for item in raw_ingredients]
    parsed = [parse_quantity_string(text) for text in texts]
    return [item for item in parsed if item["name"] and item["name"].strip()]


def _reparse_bug2_row(ingredient: dict) -> dict:
    """Reconstruct the original raw text from the (already-correct) amount
    + (corrupted) name and re-run it through the fixed parser -- see this
    module's docstring for why this is safe for bug-2 rows specifically."""
    amount = ingredient.get("amount")
    name = ingredient["name"]
    raw_text = f"{amount:g} {name}" if amount is not None else name
    reparsed = parse_quantity_string(raw_text)
    return {
        "name": reparsed["name"],
        "amount": reparsed["amount"],
        "unit": reparsed["unit"],
        "preparation": ingredient.get("preparation"),
    }


def _reparse_bug3_or_vocab_row(ingredient: dict) -> dict | None:
    """Generic reconstruct-and-reparse pass covering BOTH the pack-size
    fraction gap and the new pinch/dash/stalk/head/bunch unit vocabulary
    (both fixed together in `app/utils/quantity_parser.py`, same day as
    bug 2). Returns None if reparsing the reconstructed text doesn't
    resolve any new unit (i.e. this row isn't actually corrupted by either
    of these two bugs -- leave it untouched rather than guess). The
    original `amount` is always kept verbatim; only `name`/`unit` are
    ever replaced, so this can never introduce a numeric drift.
    """
    amount = ingredient.get("amount")
    name = ingredient["name"]
    if amount is None:
        # No leading amount at all -- neither bug can apply (both require a
        # unit word immediately following a recognized leading amount).
        return None
    raw_text = f"{amount:g} {name}"
    reparsed = parse_quantity_string(raw_text)
    if reparsed["unit"] is None:
        # Reparsing didn't newly resolve a unit -- not a bug-3/vocab row.
        return None
    return {
        "name": reparsed["name"],
        "amount": amount,
        "unit": reparsed["unit"],
        "preparation": ingredient.get("preparation"),
    }


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report stats; write nothing.")
    args = parser.parse_args()

    settings = get_settings()
    corpus_path = Path(settings.recipe_path).parent / "imported_recipes.jsonl"
    print(f"Corpus: {corpus_path}")

    records = _read_jsonl(corpus_path)
    print(f"Loaded {len(records)} corpus recipes.")

    bug1_recipe_ids = [
        record["recipe_id"] for record in records if any(_is_bug1_row(ing) for ing in record["ingredients"])
    ]
    bug2_only_recipe_ids = [
        record["recipe_id"]
        for record in records
        if record["recipe_id"] not in bug1_recipe_ids
        and any(_is_bug2_row(ing) for ing in record["ingredients"])
    ]
    print(
        f"\nRecipes with >=1 bug-1 (fraction-range) row: {len(bug1_recipe_ids)}\n"
        f"Recipes with >=1 bug-2 (container-word) row (excluding bug-1 overlap): "
        f"{len(bug2_only_recipe_ids)}"
    )

    # --- Bug 2: reconstruct-and-reparse, no archive lookup needed. ---------
    bug2_rows_fixed = 0
    bug2_rows_seen = 0
    bug2_rows_still_polluted = 0
    for record in records:
        for ingredient in record["ingredients"]:
            if not _is_bug2_row(ingredient):
                continue
            bug2_rows_seen += 1
            fixed = _reparse_bug2_row(ingredient)
            if _is_bug2_row(fixed):
                # Fixed vocabulary didn't resolve it (shouldn't happen for a
                # true bug-2 row) -- leave untouched and flag loudly.
                bug2_rows_still_polluted += 1
                print(f"  ** WARNING: bug-2 row still polluted after reparse: {record['recipe_id']} {ingredient!r}")
                continue
            ingredient["name"] = fixed["name"]
            ingredient["amount"] = fixed["amount"]
            ingredient["unit"] = fixed["unit"]
            bug2_rows_fixed += 1

    print(f"\nBug-2 rows seen: {bug2_rows_seen}, fixed: {bug2_rows_fixed}, still polluted: {bug2_rows_still_polluted}")

    # --- Bug 1: needs raw archive text. -------------------------------------
    print("\nIndexing archive directories for bug-1 recipes...")
    stem_index = _build_stem_index(_ARCHIVE_DIRS_PRIORITY)
    print(f"  {sum(len(v) for v in stem_index.values())} files across {len(stem_index)} unique foodcom_id stems.")

    records_by_id = {record["recipe_id"]: record for record in records}
    bug1_rows_seen = 0
    bug1_rows_fixed = 0
    bug1_rows_still_polluted = 0
    unresolved_reasons: Counter = Counter()
    count_mismatches: list[str] = []

    for recipe_id in bug1_recipe_ids:
        record = records_by_id[recipe_id]
        source_url = record.get("source_url")
        candidates = stem_index.get(str(source_url), []) if source_url else []
        jsonld, failure_reason = _find_verified_source(candidates, recipe_id)

        current_ingredients = record["ingredients"]
        bug1_indices = [i for i, ing in enumerate(current_ingredients) if _is_bug1_row(ing)]
        bug1_rows_seen += len(bug1_indices)

        if jsonld is None:
            unresolved_reasons[failure_reason] += len(bug1_indices)
            print(f"  ** could not verify archive source for {recipe_id} ({failure_reason}) -- left untouched.")
            continue

        reparsed_all = _reparsed_raw_ingredients(jsonld)
        if len(reparsed_all) != len(current_ingredients):
            count_mismatches.append(recipe_id)
            unresolved_reasons["ingredient_count_mismatch"] += len(bug1_indices)
            print(
                f"  ** ingredient count mismatch for {recipe_id}: "
                f"corpus={len(current_ingredients)} vs archive-reparse={len(reparsed_all)} -- left untouched."
            )
            continue

        for i in bug1_indices:
            fixed = reparsed_all[i]
            if _is_bug1_row(fixed):
                bug1_rows_still_polluted += 1
                print(f"  ** WARNING: bug-1 row still polluted after reparse: {recipe_id} {fixed!r}")
                continue
            current_ingredients[i]["name"] = fixed["name"]
            current_ingredients[i]["amount"] = fixed["amount"]
            current_ingredients[i]["unit"] = fixed["unit"]
            bug1_rows_fixed += 1

    print(
        f"\nBug-1 rows seen: {bug1_rows_seen}, fixed: {bug1_rows_fixed}, "
        f"still polluted: {bug1_rows_still_polluted}, "
        f"unresolved (no verified source / count mismatch): "
        f"{bug1_rows_seen - bug1_rows_fixed - bug1_rows_still_polluted}"
    )
    if unresolved_reasons:
        print(f"  unresolved breakdown: {dict(unresolved_reasons)}")
    if count_mismatches:
        print(f"  recipes with ingredient-count mismatch (left fully untouched): {count_mismatches}")

    # --- Bug 3 / vocab expansion: reconstruct-and-reparse, no archive lookup
    # needed (same mechanism as bug 2 -- see _reparse_bug3_or_vocab_row). Runs
    # AFTER bug 1/2 so it only ever considers rows still `unit is None` at
    # this point (i.e. never re-touches an already-fixed bug-1/bug-2 row). ---
    bug3_rows_seen = 0
    bug3_rows_fixed = 0
    for record in records:
        for ingredient in record["ingredients"]:
            if ingredient.get("unit") is not None:
                continue
            bug3_rows_seen += 1
            fixed = _reparse_bug3_or_vocab_row(ingredient)
            if fixed is None:
                continue
            ingredient["name"] = fixed["name"]
            ingredient["amount"] = fixed["amount"]
            ingredient["unit"] = fixed["unit"]
            bug3_rows_fixed += 1

    print(
        f"\nBug-3/vocab-expansion candidate rows examined (unit is None after "
        f"bugs 1/2): {bug3_rows_seen}, newly resolved a unit: {bug3_rows_fixed}"
    )

    # --- Final corpus-wide signature counts (verification). -----------------
    final_bug1 = sum(1 for r in records for ing in r["ingredients"] if _is_bug1_row(ing))
    final_bug2_start = sum(1 for r in records for ing in r["ingredients"] if _is_bug2_row(ing))
    print(f"\nFinal corpus-wide bug-1 signature rows remaining: {final_bug1}")
    print(f"Final corpus-wide bug-2 (start-anchored) signature rows remaining: {final_bug2_start}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    records.sort(key=lambda r: r["recipe_id"])
    _write_jsonl_atomic(corpus_path, records)
    print(f"\nWrote {len(records)} recipes -> {corpus_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
