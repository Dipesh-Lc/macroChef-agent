"""One-time (re-runnable/idempotent) corpus cleanup: remove recipes flagged
by an integrity audit from `imported_recipes.jsonl` and move them, with
their full data and the reason, into a quarantine sidecar.

Two checks are available via `--check {title,instructions}` (default
`title`, unchanged from before this flag existed):
  - `title` (`audit_title_ingredient_integrity` /
    `title_ingredient_integrity`): does the recipe's TITLE name an allergen
    absent from its own ingredients/allergens?
  - `instructions` (`audit_instructions_integrity` /
    `instructions_ingredient_integrity`): does the recipe's INSTRUCTIONS
    text name a Tier A/B safety-relevant food (allergen category, animal
    flesh, or undisclosed stock -- see `docs/instructions_integrity_spec.md`)
    absent from its own ingredients/allergens? Tier C (report-only)
    mismatches from that check are never used to select rows here -- see
    that module's `tier_ab_mismatches`.
Both checks share the exact same merge-by-id/first-decision-wins/
atomic-write path below, untouched by which check produced the mismatches.

Why quarantine and not repair: a flagged recipe's ingredient list is
provably incomplete (its own title or its own instructions names a food
that appears nowhere in the ingredients or the derived `allergens` field)
-- so the row is UNTRUSTWORTHY, not merely mislabeled. We cannot know what
else its ingredient list is missing. Enriching it from the instructions text
would be a guess about a safety-critical field, which this project does not
do (the LLM never enforces allergies or invents missing ingredient facts).
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
files unchanged.

The quarantine sidecar is a safety AUDIT TRAIL, not a derived/rebuildable
artifact, so this script never overwrites it wholesale. Every run MERGES
its newly-flagged records into whatever is already on disk at
`--quarantine-path`, keyed by recipe id: an id already present keeps its
EXISTING row and reason untouched (first quarantine decision wins; the
script prints a note when a run re-flags an id that's already quarantined),
and only genuinely new ids are appended. The merged result is written
atomically (temp file + `os.replace`) so a crash mid-write can never
truncate the sidecar. (A prior version of this script overwrote the sidecar
by default on every run, which once silently clobbered a 177-row audit
record down to 9 rows on a later batch -- see git history. This merge
behavior is the fix; there is no longer an opt-in "append" flag because
merging is now always the behavior.)

Usage:
    python scripts/quarantine_flagged_recipes.py
    python scripts/quarantine_flagged_recipes.py --dry-run

Manual mode -- quarantining specific recipe ids by explicit id, bypassing the
`title_ingredient_integrity` audit scan entirely:

    python scripts/quarantine_flagged_recipes.py \\
        --recipe-ids imp_78c1d567c07b545a --reason "..."

This exists for cases neither audit's hand-authored vocabulary can see (e.g.
a title word like "beef" or "fish" that is a MEAT_ALIASES/species word, not
in TITLE_ALLERGEN_CATEGORIES) but which is proven corrupt by other means --
e.g. adjudication of a benchmark case against the row's own instructions
column. `--recipe-ids` accepts one or more ids;
`--reason` is a single free-text string applied to all ids given in that
invocation (run the command once per id if each needs a distinct citation).
It reuses the exact same merge-by-id / first-decision-wins / atomic-write
path as the audit-scan mode above -- it only replaces how the SET of
recipe ids to quarantine is decided, never how they are written. Recipe ids
not found in the corpus are reported as errors and the run aborts without
writing anything (all-or-nothing).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.recipe import Recipe  # noqa: E402
from app.services.corpus_import import instructions_ingredient_integrity  # noqa: E402
from app.services.corpus_import import title_ingredient_integrity  # noqa: E402
from scripts import audit_instructions_integrity  # noqa: E402
from scripts.audit_title_ingredient_integrity import DEFAULT_CORPUS_PATH, _load_corpus, audit  # noqa: E402

DEFAULT_QUARANTINE_PATH = DEFAULT_CORPUS_PATH.parent / "quarantined_recipes.jsonl"


@dataclass
class _CheckAdapter:
    """Uniform interface over the two available checks so `main()` below
    doesn't need to branch on `--check` beyond selecting the adapter once.
    `mismatches_by_id` is deliberately the ONLY tier-aware step: for the
    `instructions` check it must return Tier A/B mismatches ONLY (Tier C is
    report-only and must never select a row for quarantine here) -- see
    `instructions_ingredient_integrity.tier_ab_mismatches`.
    """

    name: str
    mismatches_by_id: Callable[[list[Recipe]], dict[str, list]]
    build_quarantine_record: Callable[[Recipe, list], dict]


def _title_mismatches_by_id(corpus: list[Recipe]) -> dict[str, list]:
    result = audit(corpus)
    mismatches_by_id: dict[str, list] = {}
    for mismatch in result.mismatches:
        mismatches_by_id.setdefault(mismatch.recipe_id, []).append(mismatch)
    return mismatches_by_id


def _instructions_mismatches_by_id(corpus: list[Recipe]) -> dict[str, list]:
    result = audit_instructions_integrity.audit(corpus)
    mismatches_by_id: dict[str, list] = {}
    # Tier A/B ONLY -- Tier C mismatches are report-only and must never
    # cause a row to be selected for quarantine here (spec Sec. 3's
    # decision rule).
    for mismatch in result.quarantine_mismatches():
        mismatches_by_id.setdefault(mismatch.recipe_id, []).append(mismatch)
    return mismatches_by_id


_CHECKS: dict[str, _CheckAdapter] = {
    "title": _CheckAdapter(
        name="title",
        mismatches_by_id=_title_mismatches_by_id,
        build_quarantine_record=title_ingredient_integrity.build_quarantine_record,
    ),
    "instructions": _CheckAdapter(
        name="instructions",
        mismatches_by_id=_instructions_mismatches_by_id,
        build_quarantine_record=instructions_ingredient_integrity.build_quarantine_record,
    ),
}


def _write_corpus(path: Path, recipes: list[Recipe]) -> None:
    recipes = sorted(recipes, key=lambda recipe: recipe.recipe_id)
    with path.open("w", encoding="utf-8") as handle:
        for recipe in recipes:
            handle.write(json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")


def _load_existing_quarantine(path: Path) -> dict[str, dict]:
    """Load the existing quarantine sidecar (if any), keyed by recipe id.
    Returns {} if the file doesn't exist yet -- the fresh-run case."""
    existing: dict[str, dict] = {}
    if not path.exists():
        return existing
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            existing[record["recipe"]["recipe_id"]] = record
    return existing


def _merge_quarantine_records(existing: dict[str, dict], new_records: list[dict]) -> tuple[list[dict], int]:
    """Merge this run's newly-flagged records into the existing sidecar
    contents. An id already present in `existing` KEEPS its existing row and
    reason untouched -- the first quarantine decision wins, per this
    project's never-silently-lose-safety-audit-data rule. Returns
    (merged_records_sorted_by_id, count_of_re-flagged_ids_skipped)."""
    merged = dict(existing)
    skipped = 0
    for record in new_records:
        recipe_id = record["recipe"]["recipe_id"]
        if recipe_id in merged:
            skipped += 1
            print(
                f"NOTE: recipe id {recipe_id!r} is already in the quarantine sidecar -- "
                "keeping its existing reason, skipping this run's re-flag."
            )
            continue
        merged[recipe_id] = record
    ordered = [merged[recipe_id] for recipe_id in sorted(merged)]
    return ordered, skipped


def _write_quarantine_atomic(path: Path, records: list[dict]) -> None:
    """Write the FULL merged sidecar atomically: build the complete new
    contents in a temp file in the same directory, then `os.replace()` it
    over the real path. A crash or interruption mid-write therefore can
    never leave a truncated/partial sidecar -- the real file is only ever
    swapped for a complete new one, never edited in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.remove(tmp_name)
        raise


def _build_manual_quarantine_record(recipe: Recipe, reason: str) -> dict:
    """Sidecar record for `--recipe-ids` manual mode: same top-level shape
    (`recipe` / `quarantine_reason` / `quarantined_at_utc`) as
    `title_ingredient_integrity.build_quarantine_record`, so every consumer
    of the sidecar (merge logic, any future reader) sees one consistent
    record shape regardless of which mode flagged the row. `check` is set to
    "manual_adjudication" (as opposed to "title_ingredient_integrity") so the
    provenance of the decision stays visible in the data."""
    return {
        "recipe": recipe.model_dump(mode="json"),
        "quarantine_reason": {
            "check": "manual_adjudication",
            "explanation": reason,
        },
        "quarantined_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _run_manual_quarantine(
    corpus_path: Path, quarantine_path: Path, recipe_ids: list[str], reason: str, *, dry_run: bool
) -> int:
    corpus = _load_corpus(corpus_path)
    by_id = {recipe.recipe_id: recipe for recipe in corpus}

    missing = [recipe_id for recipe_id in recipe_ids if recipe_id not in by_id]
    if missing:
        print(f"ERROR: recipe id(s) not found in {corpus_path}: {missing}. Aborting -- no files written.")
        return 1

    requested = set(recipe_ids)
    kept = [recipe for recipe in corpus if recipe.recipe_id not in requested]
    quarantined = [by_id[recipe_id] for recipe_id in recipe_ids]

    print(f"Loaded {len(corpus)} recipes from {corpus_path}")
    print(f"Manually flagged for quarantine: {len(quarantined)} {sorted(requested)}")
    print(f"Remaining after quarantine: {len(kept)}")

    if dry_run:
        print("\n--dry-run: no files written.")
        return 0

    quarantine_records = [_build_manual_quarantine_record(recipe, reason) for recipe in quarantined]

    existing_quarantine = _load_existing_quarantine(quarantine_path)
    merged_records, skipped = _merge_quarantine_records(existing_quarantine, quarantine_records)
    newly_added = len(quarantine_records) - skipped

    _write_corpus(corpus_path, kept)
    _write_quarantine_atomic(quarantine_path, merged_records)

    print(f"\nWrote {len(kept)} recipes to {corpus_path}")
    print(
        f"Wrote {len(merged_records)} total quarantined recipes to {quarantine_path} "
        f"({newly_added} newly added this run, {skipped} re-flagged id(s) skipped (kept existing reason), "
        f"{len(existing_quarantine)} carried over from prior runs)"
    )
    return 0


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
        "--check",
        choices=sorted(_CHECKS),
        default="title",
        help=(
            "Which integrity audit to scan with: 'title' (default, unchanged) or "
            "'instructions' (docs/instructions_integrity_spec.md; Tier A/B mismatches only -- "
            "Tier C report-only findings are never used to select a row here). Ignored in "
            "--recipe-ids manual mode, which bypasses both audit scans entirely."
        ),
    )
    parser.add_argument(
        "--recipe-ids",
        nargs="+",
        default=None,
        help=(
            "Manual mode: quarantine these exact recipe id(s) directly, bypassing the "
            "audit scan selected by --check. Requires --reason."
        ),
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Reason text for --recipe-ids manual mode (applied to every id given in this invocation).",
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus_path)
    quarantine_path = Path(args.quarantine_path)

    if args.recipe_ids is not None:
        if not args.reason:
            parser.error("--reason is required when --recipe-ids is given")
        return _run_manual_quarantine(
            corpus_path, quarantine_path, args.recipe_ids, args.reason, dry_run=args.dry_run
        )

    check = _CHECKS[args.check]
    corpus = _load_corpus(corpus_path)
    mismatches_by_id = check.mismatches_by_id(corpus)

    kept = [recipe for recipe in corpus if recipe.recipe_id not in mismatches_by_id]
    quarantined = [recipe for recipe in corpus if recipe.recipe_id in mismatches_by_id]

    print(f"Loaded {len(corpus)} recipes from {corpus_path}")
    print(f"Check: {check.name}")
    print(f"Flagged for quarantine: {len(quarantined)} ({len(quarantined) / len(corpus):.2%})")
    print(f"Remaining after quarantine: {len(kept)}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    quarantine_records = [
        check.build_quarantine_record(recipe, mismatches_by_id[recipe.recipe_id]) for recipe in quarantined
    ]

    existing_quarantine = _load_existing_quarantine(quarantine_path)
    merged_records, skipped = _merge_quarantine_records(existing_quarantine, quarantine_records)
    newly_added = len(quarantine_records) - skipped

    _write_corpus(corpus_path, kept)
    _write_quarantine_atomic(quarantine_path, merged_records)

    print(f"\nWrote {len(kept)} recipes to {corpus_path}")
    print(
        f"Wrote {len(merged_records)} total quarantined recipes to {quarantine_path} "
        f"({newly_added} newly added this run, {skipped} re-flagged id(s) skipped (kept existing reason), "
        f"{len(existing_quarantine)} carried over from prior runs)"
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
