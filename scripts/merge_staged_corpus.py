"""Merge the four staged 2026-07-25 corpus-expansion batches (gap, ext1,
ext2, ext3) into the REAL production sidecars -- the first actual merge of
this staged work (every prior session deliberately kept it separate). Three
independent merges, each with its own collision assert; any assert failure
STOPS the script rather than papering over it:

  (a) imported_recipes.jsonl: current corpus + the cross-batch-deduped
      combined batch (candidate_batch_combined_all4_deduped_20260725.jsonl,
      6,128 recipes), plus one more independent safety net -- a fresh
      `RecipeDedupService.deduplicate()` run of the staged recipes against
      TODAY's actual production corpus (`load_corpus()`), not a stale
      snapshot from when staging began. Any new duplicate found here is
      dropped from the merge, and the corrected total is reported honestly.
  (b) quarantined_recipes.jsonl: current quarantine + the four staged
      per-batch quarantine sidecars (pure audit trail, never read at serve
      time).
  (c) grounding.jsonl: current grounding sidecar + the four staged per-batch
      grounding sidecars, FILTERED to only the recipe_ids that actually
      survive into (a) above (a cross-batch or fresh-dedup drop must not
      leave an orphaned grounding row for a recipe that isn't in the corpus).

Never touches the production Chroma collection -- reindexing is a separate
step (see the merge task's step 6).

Usage:
    python scripts/merge_staged_corpus.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.rag.loaders import load_corpus, load_recipes  # noqa: E402
from app.services.recipe_dedup_service import RecipeDedupService  # noqa: E402
from scripts.cross_batch_dedup_check import _recipe_to_candidate  # noqa: E402  (reused as-is)
from scripts.import_corpus import _write_jsonl_records_atomic  # noqa: E402  (reused as-is)

settings = get_settings()
DATA_DIR = Path(settings.recipe_path).parent

IMPORTED_PATH = DATA_DIR / "imported_recipes.jsonl"
QUARANTINE_PATH = DATA_DIR / "quarantined_recipes.jsonl"
GROUNDING_PATH = DATA_DIR / "grounding.jsonl"

STAGED_COMBINED = DATA_DIR / "candidate_batch_combined_all4_deduped_20260725.jsonl"
QUARANTINE_SIDECARS = [
    DATA_DIR / "candidate_batch_quarantine_20260725.jsonl",
    DATA_DIR / "candidate_batch_ext_quarantine_20260725.jsonl",
    DATA_DIR / "candidate_batch_ext2_quarantine_20260725.jsonl",
    DATA_DIR / "candidate_batch_ext3_quarantine_20260725.jsonl",
]
GROUNDING_SIDECARS = [
    DATA_DIR / "candidate_batch_grounding_20260725.jsonl",
    DATA_DIR / "candidate_batch_ext_grounding_20260725.jsonl",
    DATA_DIR / "candidate_batch_ext2_grounding_20260725.jsonl",
    DATA_DIR / "candidate_batch_ext3_grounding_20260725.jsonl",
]


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> int:
    # --- (a) Corpus merge ---
    current_imported = load_recipes(IMPORTED_PATH)
    staged = load_recipes(STAGED_COMBINED)
    print(f"Current imported_recipes.jsonl: {len(current_imported)}")
    print(f"Staged combined batch (cross-batch-deduped): {len(staged)}")

    combined_ids = [r.recipe_id for r in current_imported] + [r.recipe_id for r in staged]
    assert len(set(combined_ids)) == len(combined_ids), (
        "recipe_id collision between current imported corpus and staged batch -- STOP"
    )
    print("OK: zero recipe_id collisions between current corpus and staged batch.")

    # Independent fresh safety net: re-run RecipeDedupService against TODAY's
    # actual production state (seeds + imported_recipes.jsonl via load_corpus(),
    # itself built from load_recipes()), not a stale snapshot from when
    # staging began.
    production_recipes = load_corpus()
    print(f"Fresh cross-check base: {len(production_recipes)} current production recipes (seeds + imported).")
    staged_candidates = [_recipe_to_candidate(recipe, "combined") for recipe in staged]
    dedup_result = RecipeDedupService().deduplicate(staged_candidates, existing_recipes=production_recipes)
    new_dupes = {candidate.candidate_id for candidate in dedup_result.duplicate_candidates}
    if new_dupes:
        print(f"WARNING: fresh cross-check found {len(new_dupes)} NEW duplicate(s) not caught at per-batch import time:")
        for candidate_id in sorted(new_dupes):
            print(f"  - {candidate_id}: {dedup_result.duplicate_reasons.get(candidate_id)}")
    else:
        print("OK: fresh cross-check against today's production state found zero new duplicates.")

    survivor_ids = {recipe.recipe_id for recipe in staged} - new_dupes
    survivors = [recipe for recipe in staged if recipe.recipe_id in survivor_ids]
    merged_corpus = sorted(current_imported + survivors, key=lambda recipe: recipe.recipe_id)
    print(f"Final merged imported_recipes.jsonl: {len(merged_corpus)} recipes ({len(survivors)} new survivors).")

    _write_jsonl_records_atomic(IMPORTED_PATH, [recipe.model_dump(mode="json") for recipe in merged_corpus])
    print(f"Wrote {IMPORTED_PATH}")

    # --- (b) Quarantine merge (pure audit trail) ---
    current_quarantine = _read_jsonl(QUARANTINE_PATH)
    staged_quarantine: list[dict] = []
    for path in QUARANTINE_SIDECARS:
        staged_quarantine.extend(_read_jsonl(path))
    all_quarantine = current_quarantine + staged_quarantine
    quarantine_ids = [record["recipe"]["recipe_id"] for record in all_quarantine]
    assert len(set(quarantine_ids)) == len(quarantine_ids), (
        "recipe_id collision in merged quarantine sidecar -- STOP"
    )
    print(f"OK: zero recipe_id collisions in merged quarantine ({len(all_quarantine)} records).")
    _write_jsonl_records_atomic(QUARANTINE_PATH, all_quarantine)
    print(f"Wrote {QUARANTINE_PATH}")

    # --- (c) Grounding merge ---
    current_grounding = _read_jsonl(GROUNDING_PATH)
    staged_grounding: list[dict] = []
    for path in GROUNDING_SIDECARS:
        staged_grounding.extend(_read_jsonl(path))
    # Only keep rows for recipes that actually survived into the merged
    # corpus above -- a cross-batch or fresh-dedup drop must never leave an
    # orphaned grounding row for a recipe_id that isn't in imported_recipes.jsonl.
    staged_grounding_filtered = [row for row in staged_grounding if row["recipe_id"] in survivor_ids]
    dropped = len(staged_grounding) - len(staged_grounding_filtered)
    if dropped:
        print(f"Dropped {dropped} staged grounding row(s) for recipe_ids that did not survive the corpus merge.")
    merged_grounding = sorted(current_grounding + staged_grounding_filtered, key=lambda row: row["recipe_id"])

    expected_count = len(current_grounding) + len(survivors)
    if len(merged_grounding) != expected_count:
        raise SystemExit(
            f"STOP: merged grounding.jsonl count {len(merged_grounding)} != expected {expected_count} "
            f"({len(current_grounding)} current + {len(survivors)} new survivors). Investigate before proceeding."
        )
    print(f"OK: merged grounding.jsonl count reconciles: {len(merged_grounding)} == {expected_count}")

    _write_jsonl_records_atomic(GROUNDING_PATH, merged_grounding)
    print(f"Wrote {GROUNDING_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
