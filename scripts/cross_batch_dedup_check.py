"""Cross-batch near-duplicate check for the 2026-07-25 corpus-expansion
effort (final consolidation step).

Every staged batch (gap, ext1, ext2, ext3) was deduped only against the
existing production+seed+quarantine pool at import time -- never against
EACH OTHER using the real near-duplicate fingerprint logic
(`RecipeDedupService`, the same service every batch's import already used
against the production pool). This script runs that same service across the
combined set of all four staged batches AGAINST ITSELF (existing_recipes=[],
since the production comparison already happened per-batch) and reports:

- how many near-duplicate pairs exist across batches
- the corrected net-new total after removing cross-batch duplicates

Tie-break rule: batches are concatenated in ascending Food.com id order
(gap [38-7904] -> ext1 [7905-9905] -> ext2 [9906-13905] -> ext3
[13906-15905] -- already disjoint, already ascending per their own staging
commits). `RecipeDedupService.deduplicate` keeps the FIRST occurrence of any
duplicate cluster and marks every later one as a duplicate, so processing in
this order means the recipe from the batch with the LOWEST Food.com id in a
duplicate cluster is always the one kept.

Read-only: never writes to any staged batch file, `imported_recipes.jsonl`,
`quarantined_recipes.jsonl`, `grounding.jsonl`, or the production Chroma
collection.

Usage:
    python scripts/cross_batch_dedup_check.py
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.loaders import load_recipes  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.schemas.recipe_candidate import RecipeCandidate  # noqa: E402
from app.services.recipe_dedup_service import RecipeDedupService  # noqa: E402

BATCHES = [
    ("gap", ROOT / "data/processed/candidate_batch_20260725.jsonl"),
    ("ext1", ROOT / "data/processed/candidate_batch_ext_20260725.jsonl"),
    ("ext2", ROOT / "data/processed/candidate_batch_ext2_20260725.jsonl"),
    ("ext3", ROOT / "data/processed/candidate_batch_ext3_20260725.jsonl"),
]


def _recipe_to_candidate(recipe: Recipe, batch_name: str) -> RecipeCandidate:
    """Round-trip a staged batch's Recipe rows back into RecipeCandidate
    shape so the unmodified `RecipeDedupService` (which operates on
    RecipeCandidate vs. Recipe) can be reused as-is, with no reimplementation
    of its title-similarity/ingredient-overlap logic."""
    return RecipeCandidate(
        candidate_id=recipe.recipe_id,
        title=recipe.title,
        cuisine=recipe.cuisine,
        meal_type=recipe.meal_type,
        description=recipe.description,
        ingredients=list(recipe.ingredients),
        instructions=list(recipe.instructions),
        cook_time_min=recipe.cook_time_min,
        difficulty=recipe.difficulty,
        servings=recipe.servings,
        calories=recipe.calories,
        protein_g=recipe.protein_g,
        carbs_g=recipe.carbs_g,
        fat_g=recipe.fat_g,
        fiber_g=recipe.fiber_g,
        allergens=list(recipe.allergens),
        diet_tags=list(recipe.diet_tags),
        equipment=list(recipe.equipment),
        image_url=recipe.image_url,
        image_path=recipe.image_path,
        source_type=recipe.source_type,
        source_name=recipe.source_name,
        source_url=recipe.source_url,
    )


def main() -> int:
    all_candidates: list[RecipeCandidate] = []
    counts: dict[str, int] = {}
    origin: dict[str, str] = {}  # candidate_id -> batch name, for reporting

    for name, path in BATCHES:
        recipes = load_recipes(path)
        counts[name] = len(recipes)
        for recipe in recipes:
            candidate = _recipe_to_candidate(recipe, name)
            origin[candidate.candidate_id] = name
            all_candidates.append(candidate)

    total_staged = sum(counts.values())
    print("=== Cross-batch near-duplicate check (all four staged batches vs. EACH OTHER) ===")
    for name, _ in BATCHES:
        print(f"  {name}: {counts[name]}")
    print(f"  TOTAL staged (pre-cross-batch-dedup): {total_staged}\n")

    print("Running RecipeDedupService's SAME per-candidate duplicate check "
          f"(unmodified `_find_duplicate` -- not reimplemented) across all staged "
          f"candidates ({total_staged} items, O(n^2) title/ingredient comparison -- "
          "this can take a while; progress printed every 250 items)...", flush=True)

    service = RecipeDedupService()
    unique_candidates: list[RecipeCandidate] = []
    duplicate_candidates: list[RecipeCandidate] = []
    duplicate_reasons: dict[str, str] = {}

    start = time.monotonic()
    for i, candidate in enumerate(all_candidates, start=1):
        is_dup, reason = service._find_duplicate(candidate, [], unique_candidates)
        if is_dup:
            duplicate_candidates.append(candidate)
            duplicate_reasons[candidate.candidate_id] = reason
        else:
            unique_candidates.append(candidate)
        if i % 250 == 0 or i == total_staged:
            elapsed = time.monotonic() - start
            print(
                f"  ...{i}/{total_staged} processed ({len(duplicate_candidates)} dup(s) "
                f"so far, {elapsed:.1f}s elapsed)",
                flush=True,
            )

    print(f"\nUnique after cross-batch dedup: {len(unique_candidates)}")
    print(f"Cross-batch duplicate pairs found: {len(duplicate_candidates)}\n")

    if duplicate_candidates:
        print("Duplicate details (kept-from-batch is whichever batch's copy survived):")
        for candidate in duplicate_candidates:
            reason = duplicate_reasons.get(candidate.candidate_id, "")
            dup_batch = origin.get(candidate.candidate_id, "?")
            print(
                f"  - [{dup_batch}] {candidate.candidate_id!r} {candidate.title!r} "
                f"(foodcom_id={candidate.source_url}) -- {reason}"
            )

    print(f"\nCorrected net-new staged total: {len(unique_candidates)}")
    print(f"Removed as cross-batch duplicates: {len(duplicate_candidates)}")

    # Write the corrected, cross-batch-deduped combined batch (Recipe-format
    # JSONL, matching every prior staged-batch file's shape) for Task 2's
    # combined safety benchmark to consume -- staging-only output, same class
    # of file as candidate_batch_combined_all3_20260725.jsonl.
    kept_ids = {candidate.candidate_id for candidate in unique_candidates}
    all_recipes: list[Recipe] = []
    for name, path in BATCHES:
        all_recipes.extend(load_recipes(path))
    deduped_recipes = [recipe for recipe in all_recipes if recipe.recipe_id in kept_ids]
    deduped_recipes.sort(key=lambda recipe: recipe.recipe_id)

    output_path = ROOT / "data/processed/candidate_batch_combined_all4_deduped_20260725.jsonl"
    with output_path.open("w", encoding="utf-8") as handle:
        for recipe in deduped_recipes:
            handle.write(json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
    print(f"\nWrote corrected combined+deduped batch ({len(deduped_recipes)} recipes) -> {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
