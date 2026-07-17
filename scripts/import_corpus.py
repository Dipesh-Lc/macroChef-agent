"""Import an external recipe dataset into the corpus and rebuild the index.

Usage:
    python scripts/import_corpus.py --dataset foodcom --source path/to/recipes.csv --limit 5000

Idempotent: re-running overwrites data/processed/imported_recipes.jsonl from
scratch (sorted by deterministic recipe id) and, unless --no-reindex, drops
and recreates the Chroma collection before re-indexing the union of the 25
curated seeds and the freshly imported recipes -- so a re-run with a smaller
or corrected dataset never leaves orphaned rows or stale embeddings behind.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.corpus_import.adapters import FoodComAdapter  # noqa: E402
from app.services.corpus_import.pipeline import CorpusImportPipeline  # noqa: E402
from app.services.recipe_indexing_service import RecipeIndexingService  # noqa: E402

_ADAPTERS = {
    "foodcom": FoodComAdapter,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(_ADAPTERS), required=True)
    parser.add_argument("--source", required=True, help="Path to the downloaded dataset file")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="Skip rebuilding the vector store after writing the corpus file",
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
