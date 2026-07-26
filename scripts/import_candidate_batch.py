"""Import scraped candidate archive files (Step 3 of the 2026-07-25
corpus-expansion task, Path A) into a STAGING batch -- never into the live
`data/processed/imported_recipes.jsonl` / `quarantined_recipes.jsonl`, and
never triggers a reindex of the production Chroma collection.

Reuses the exact same validation/dedup/integrity logic as a normal corpus
import (`app.services.corpus_import.adapters.FoodComScrapedArchiveAdapter`
+ `app.services.corpus_import.pipeline.CorpusImportPipeline`), just pointed
at a new candidate archive directory and NEW staging output paths.

Dedupes candidates against the union of: the 25 curated seeds, the current
`imported_recipes.jsonl`, and the current `quarantined_recipes.jsonl` (so a
candidate that happens to already be an id already-known-quarantined for a
content reason doesn't get silently re-admitted) -- but writes results ONLY
to the staging files below, and does not touch any of those three inputs.

Usage:
    python scripts/import_candidate_batch.py \\
        --archive-dir data/scraped/foodcom_candidates \\
        --output data/processed/candidate_batch_20260725.jsonl \\
        --quarantine-output data/processed/candidate_batch_quarantine_20260725.jsonl
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.rag.loaders import load_recipes  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.services.corpus_import.adapters import FoodComScrapedArchiveAdapter  # noqa: E402
from app.services.corpus_import.pipeline import CorpusImportPipeline  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    import json

    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_existing_recipes() -> list[Recipe]:
    """Union of seeds + current active corpus + current quarantine sidecar
    -- the full known-recipe universe to dedupe new candidates against.
    Read-only: never writes to any of these three files."""
    settings = get_settings()
    seeds = load_recipes(settings.recipe_path)
    imported_path = Path(settings.recipe_path).parent / "imported_recipes.jsonl"
    quarantined_path = Path(settings.recipe_path).parent / "quarantined_recipes.jsonl"

    imported = load_recipes(imported_path)
    quarantine_records = _read_jsonl(quarantined_path)
    quarantined = [Recipe.model_validate(record["recipe"]) for record in quarantine_records]

    return seeds + imported + quarantined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive-dir", default="data/scraped/foodcom_candidates")
    parser.add_argument("--output", required=True, help="Staging output path, e.g. data/processed/candidate_batch_<date>.jsonl")
    parser.add_argument(
        "--quarantine-output",
        required=True,
        help="Staging quarantine sidecar path, e.g. data/processed/candidate_batch_quarantine_<date>.jsonl",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    quarantine_output_path = Path(args.quarantine_output)

    print(f"=== Candidate batch staging import ({args.archive_dir}) ===")
    print(f"Staging output: {output_path}")
    print(f"Staging quarantine: {quarantine_output_path}")
    print("(Live imported_recipes.jsonl / quarantined_recipes.jsonl are NOT touched by this script.)")

    existing_recipes = _load_existing_recipes()
    print(f"Deduping against {len(existing_recipes)} known recipes (seeds + active corpus + quarantine sidecar).")

    adapter = FoodComScrapedArchiveAdapter()
    pipeline = CorpusImportPipeline(adapter)
    report = pipeline.run(
        args.archive_dir,
        output_path,
        existing_recipes=existing_recipes,
        quarantine_path=quarantine_output_path,
    )

    print(f"\n{report.summary()}")
    print(f"Wrote {report.survivors} staged recipes -> {output_path}")
    print(f"Wrote {len(report.quarantine_records)} staging-quarantined recipes -> {quarantine_output_path}")

    if report.example_title_ingredient_mismatches:
        print(f"\nExample title/ingredient integrity quarantines ({len(report.example_title_ingredient_mismatches)}):")
        for example in report.example_title_ingredient_mismatches:
            print(f"  - {example['title']!r} ({example['recipe_id']}) -- categories: {example['categories']}")

    if report.example_instructions_ingredient_mismatches:
        print(
            f"\nExample instructions/ingredient integrity quarantines "
            f"({len(report.example_instructions_ingredient_mismatches)}):"
        )
        for example in report.example_instructions_ingredient_mismatches:
            print(f"  - {example['title']!r} ({example['recipe_id']}) -- categories: {example['categories']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
