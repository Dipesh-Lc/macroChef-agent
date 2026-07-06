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

    examples = getattr(adapter, "example_dropped_below_min", [])
    if examples:
        print(f"\nExample recipes rejected BECAUSE OF cleaning ({len(examples)} shown):")
        for example in examples:
            print(f"\n--- {example['title']} ---")
            print("Original steps:")
            for step in example["original_instructions"]:
                print(f"  - {step}")
            print(f"Cleaned steps (survivors): {example['cleaned_instructions'] or '(none)'}")

    if not args.no_reindex:
        indexed = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=True)
        print(f"\nRebuilt vector store (clean): {indexed} recipes indexed.")


if __name__ == "__main__":
    main()
