"""One-off, idempotent, re-runnable enrichment pass: populate `cuisine`,
`meal_type`, `cuisine_source`, `meal_type_source` on every recipe currently
in `data/processed/imported_recipes.jsonl` by re-reading each recipe's own
scraped-archive source file (`data/scraped/foodcom*/<foodcom_id>.md`) and
running it through the exact same deterministic tag-matching logic
`FoodComScrapedArchiveAdapter` now applies to every FUTURE import
(`app.services.corpus_import.cuisine_tagger.resolve_cuisine` /
`app.services.corpus_import.adapters.resolve_meal_type`).

Deliberately a TARGETED ENRICHMENT, not a full pipeline re-run
(`scripts/import_corpus.py --dataset foodcom_scraped_archive`): that
reimport path only reconciles against ONE archive directory
(`data/scraped/foodcom`, 4,235 files), but the current 9,986-recipe corpus
was assembled from FIVE scrape batches (`data/scraped/foodcom` +
`foodcom_candidates{,_ext,_ext2,_ext3}`, ~20,155 files total) via a
multi-step candidate-batch staging process (see
`scripts/import_candidate_batch.py`) that this script does not attempt to
replicate. Verified before writing this script: every one of the 9,986
active corpus recipes' `source_url` (foodcom_id) matches a filename stem in
at least one of the five archive directories -- re-running the
single-directory reimport instead would have silently treated every recipe
sourced from the other four directories as "unsourced" and DROPPED it from
the active corpus. This script instead:

  1. Loads the current corpus verbatim (every field preserved byte-for-byte
     except the 4 new/changed ones below).
  2. For each recipe, looks up its own `source_url` (foodcom_id) across all
     five archive directories (fixed priority order: foodcom, then
     foodcom_candidates, _ext, _ext2, _ext3) and uses the FIRST copy that
     (a) parses (frontmatter + fenced JSON-LD block), (b) has
     `http_status == "200"`, and (c) whose frontmatter `recipe_id` matches
     this recipe's OWN `recipe_id` -- an extra safety check that it's
     genuinely the same recipe's page, not a coincidental foodcom_id
     collision from a corrupted/mismatched file in a later batch.
  3. Computes cuisine/meal_type + provenance via the shared deterministic
     resolvers and updates ONLY those 4 fields -- ingredients,
     instructions, allergens, recipe_id, everything else is untouched.
  4. Writes the corpus back, same sort order (by recipe_id) and same
     atomic-write pattern as `pipeline._write_jsonl`.

Recipes whose source file can't be found/verified keep `cuisine=None`,
`cuisine_source="unknown"` (and the meal_type equivalent) -- every recipe
gets an explicit provenance marker after this script runs, distinguishing
"we tried and found nothing" from "we never checked".

Usage:
    python scripts/backfill_cuisine_meal_type_tags.py [--dry-run]
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

from app.config import get_settings  # noqa: E402
from app.services.corpus_import.adapters import (  # noqa: E402
    ScrapedArchiveIntegrityError,
    _extract_jsonld_block,
    _parse_scraped_frontmatter,
    resolve_meal_type,
)
from app.services.corpus_import.cuisine_tagger import resolve_cuisine  # noqa: E402

_ARCHIVE_DIRS_PRIORITY = [
    "data/scraped/foodcom",
    "data/scraped/foodcom_candidates",
    "data/scraped/foodcom_candidates_ext",
    "data/scraped/foodcom_candidates_ext2",
    "data/scraped/foodcom_candidates_ext3",
]


def _build_stem_index(dirs: list[str]) -> dict[str, list[Path]]:
    """foodcom_id (filename stem) -> candidate file paths, in the fixed
    directory priority order above (a stem present in multiple directories
    keeps every occurrence, tried in order until one verifies -- see
    `_find_verified_source`)."""
    index: dict[str, list[Path]] = {}
    for directory in dirs:
        path = Path(directory)
        if not path.exists():
            print(f"WARNING: archive directory missing: {path}")
            continue
        for file_path in path.glob("*.md"):
            index.setdefault(file_path.stem, []).append(file_path)
    return index


def _find_verified_source(
    candidate_paths: list[Path], expected_recipe_id: str
) -> tuple[dict | None, str | None]:
    """Tries each candidate path in priority order; returns (jsonld_dict,
    None) for the first one that parses, has http_status == "200", and
    whose frontmatter recipe_id matches `expected_recipe_id`. Returns
    (None, reason) if none of the candidates verify -- `reason` is the
    failure category of the LAST candidate tried (for the mismatch-reason
    tally), or "no_candidate_files" if `candidate_paths` was empty."""
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
    parser.add_argument("--dry-run", action="store_true", help="Report coverage stats; write nothing.")
    args = parser.parse_args()

    settings = get_settings()
    corpus_path = Path(settings.recipe_path).parent / "imported_recipes.jsonl"
    print(f"Corpus: {corpus_path}")

    print("Indexing archive directories...")
    stem_index = _build_stem_index(_ARCHIVE_DIRS_PRIORITY)
    print(f"  {sum(len(v) for v in stem_index.values())} files across {len(stem_index)} unique foodcom_id stems.")

    records = _read_jsonl(corpus_path)
    print(f"Loaded {len(records)} corpus recipes.")

    before_cuisine_nonnull = sum(1 for r in records if r.get("cuisine"))
    before_meal_type_nonnull = sum(1 for r in records if r.get("meal_type"))

    unverified_reasons: Counter = Counter()
    meal_type_source_counts: Counter = Counter()
    cuisine_source_counts: Counter = Counter()
    meal_type_changed = 0
    cuisine_changed = 0
    recovered_cuisine_examples: list[dict] = []

    for record in records:
        source_url = record.get("source_url")
        expected_recipe_id = record.get("recipe_id")
        candidates = stem_index.get(str(source_url), []) if source_url else []
        jsonld, failure_reason = _find_verified_source(candidates, expected_recipe_id)

        if jsonld is None:
            unverified_reasons[failure_reason] += 1
            raw_category = None
            raw_keywords = None
        else:
            raw_category = jsonld.get("recipeCategory")
            if isinstance(raw_category, list) and raw_category:
                raw_category = raw_category[0]
            raw_category = raw_category if isinstance(raw_category, str) else None

            raw_keywords = jsonld.get("keywords")
            if isinstance(raw_keywords, list) and raw_keywords:
                raw_keywords = ",".join(str(item) for item in raw_keywords)
            raw_keywords = raw_keywords if isinstance(raw_keywords, str) else None

        meal_type, meal_type_source = resolve_meal_type(raw_category, raw_keywords)
        cuisine, cuisine_source = resolve_cuisine(raw_category, raw_keywords)

        meal_type_source_counts[meal_type_source] += 1
        cuisine_source_counts[cuisine_source] += 1

        if record.get("meal_type") != meal_type:
            meal_type_changed += 1
        if record.get("cuisine") != cuisine:
            cuisine_changed += 1
            if cuisine and len(recovered_cuisine_examples) < 30:
                recovered_cuisine_examples.append(
                    {
                        "recipe_id": record.get("recipe_id"),
                        "title": record.get("title"),
                        "cuisine": cuisine,
                        "recipe_category": raw_category,
                        "keywords": raw_keywords,
                    }
                )

        record["cuisine"] = cuisine
        record["cuisine_source"] = cuisine_source
        record["meal_type"] = meal_type
        record["meal_type_source"] = meal_type_source

    after_cuisine_nonnull = sum(1 for r in records if r.get("cuisine"))
    after_meal_type_nonnull = sum(1 for r in records if r.get("meal_type"))
    total = len(records)

    print("\n--- Source verification ---")
    print(f"  Verified source found: {total - sum(unverified_reasons.values())}/{total}")
    if unverified_reasons:
        print(f"  Unverified breakdown: {dict(unverified_reasons)}")

    print("\n--- cuisine_source breakdown ---")
    for key, count in cuisine_source_counts.most_common():
        print(f"  {key}: {count} ({100 * count / total:.2f}%)")

    print("\n--- meal_type_source breakdown ---")
    for key, count in meal_type_source_counts.most_common():
        print(f"  {key}: {count} ({100 * count / total:.2f}%)")

    print("\n--- Coverage before -> after ---")
    print(
        f"  cuisine non-null:   {before_cuisine_nonnull}/{total} "
        f"({100 * before_cuisine_nonnull / total:.2f}%) -> "
        f"{after_cuisine_nonnull}/{total} ({100 * after_cuisine_nonnull / total:.2f}%)"
    )
    print(
        f"  meal_type non-null: {before_meal_type_nonnull}/{total} "
        f"({100 * before_meal_type_nonnull / total:.2f}%) -> "
        f"{after_meal_type_nonnull}/{total} ({100 * after_meal_type_nonnull / total:.2f}%)"
    )
    print(f"\n  cuisine field changed on {cuisine_changed} recipes.")
    print(f"  meal_type field changed on {meal_type_changed} recipes.")

    print("\n--- Sample of newly-recovered cuisine tags (up to 30) ---")
    for example in recovered_cuisine_examples:
        print(f"  {example['recipe_id']} {example['title']!r} -> {example['cuisine']!r} "
              f"(recipeCategory={example['recipe_category']!r}, keywords={example['keywords']!r})")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    records.sort(key=lambda r: r["recipe_id"])
    _write_jsonl_atomic(corpus_path, records)
    print(f"\nWrote {len(records)} recipes -> {corpus_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
