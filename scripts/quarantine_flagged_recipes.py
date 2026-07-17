"""One-time (re-runnable/idempotent) corpus cleanup: remove recipes flagged
by `audit_title_ingredient_integrity.py` from `imported_recipes.jsonl` and
move them, with their full data and the reason, into a quarantine sidecar.

Why quarantine and not repair: a flagged recipe's ingredient list is
provably incomplete (its own title names a food that appears nowhere in the
ingredients or the derived `allergens` field) -- so the row is
UNTRUSTWORTHY, not merely mislabeled. We cannot know what else its
ingredient list is missing. Enriching it from the instructions text would
be a guess about a safety-critical field, which this project does not do
(the LLM never enforces allergies or invents missing ingredient facts).
Dropping is the only sound response; quarantining (rather than a silent
delete) preserves the row for provenance/audit per this project's
never-delete-safety-relevant-data rule.

No index/Chroma rebuild is required by this script: `app.rag.loaders.
load_corpus()` reads `imported_recipes.jsonl` directly and
`RecipeRetriever.retrieve()`'s `recipes_by_id` lookup filters out any id no
longer present in that file, so a quarantined recipe stops being served the
moment this script rewrites the file -- even though it is not immediately
purged from the Chroma vector store. Removing the stale Chroma rows is a
separate, deferred hygiene task (see this task's report).

Idempotent: re-running against an already-cleaned `imported_recipes.jsonl`
finds zero new mismatches (nothing left to quarantine) and leaves both
files unchanged; it will NOT re-add anything already sitting in the
quarantine sidecar even if `--quarantine-path` points at a fresh location,
since quarantining is driven entirely by re-running the audit against
whatever is currently in `--corpus-path`.

Usage:
    python scripts/quarantine_flagged_recipes.py
    python scripts/quarantine_flagged_recipes.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.recipe import Recipe  # noqa: E402
from app.services.corpus_import.title_ingredient_integrity import (  # noqa: E402
    Mismatch,
    build_quarantine_record,
)
from scripts.audit_title_ingredient_integrity import DEFAULT_CORPUS_PATH, _load_corpus, audit  # noqa: E402

DEFAULT_QUARANTINE_PATH = DEFAULT_CORPUS_PATH.parent / "quarantined_recipes.jsonl"


def _write_corpus(path: Path, recipes: list[Recipe]) -> None:
    recipes = sorted(recipes, key=lambda recipe: recipe.recipe_id)
    with path.open("w", encoding="utf-8") as handle:
        for recipe in recipes:
            handle.write(json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")


def _write_quarantine(path: Path, records: list[dict], *, append: bool) -> None:
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-path", default=str(DEFAULT_CORPUS_PATH))
    parser.add_argument("--quarantine-path", default=str(DEFAULT_QUARANTINE_PATH))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be quarantined without writing either file.",
    )
    parser.add_argument(
        "--append-quarantine",
        action="store_true",
        help="Append to an existing quarantine sidecar instead of overwriting it "
        "(overwrite is the default -- this run's audit is a full re-scan of "
        "--corpus-path, so a fresh full quarantine file, not an accumulating "
        "append, is idempotent by construction).",
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus_path)
    quarantine_path = Path(args.quarantine_path)

    corpus = _load_corpus(corpus_path)
    result = audit(corpus)

    mismatches_by_id: dict[str, list[Mismatch]] = {}
    for mismatch in result.mismatches:
        mismatches_by_id.setdefault(mismatch.recipe_id, []).append(mismatch)

    kept = [recipe for recipe in corpus if recipe.recipe_id not in mismatches_by_id]
    quarantined = [recipe for recipe in corpus if recipe.recipe_id in mismatches_by_id]

    print(f"Loaded {len(corpus)} recipes from {corpus_path}")
    print(f"Flagged for quarantine: {len(quarantined)} ({len(quarantined) / len(corpus):.2%})")
    print(f"Remaining after quarantine: {len(kept)}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    quarantine_records = [
        build_quarantine_record(recipe, mismatches_by_id[recipe.recipe_id]) for recipe in quarantined
    ]

    _write_corpus(corpus_path, kept)
    _write_quarantine(quarantine_path, quarantine_records, append=args.append_quarantine)

    print(f"\nWrote {len(kept)} recipes to {corpus_path}")
    print(
        f"Wrote {len(quarantine_records)} quarantined recipes to {quarantine_path} "
        f"({'appended' if args.append_quarantine and quarantine_path.exists() else 'overwritten'})"
    )
    print(
        "\nNOTE: quarantined recipe ids remain in the Chroma vector store until the "
        "index is rebuilt -- app.rag.loaders.load_corpus() reads imported_recipes.jsonl "
        "directly and RecipeRetriever.retrieve() drops any id no longer present there, "
        "so they will not be served, but the stale embeddings themselves are a "
        "deferred hygiene task, not fixed by this script."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
