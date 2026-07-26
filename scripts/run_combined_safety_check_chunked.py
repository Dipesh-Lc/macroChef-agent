"""Same combined-view safety benchmark as `scripts/run_combined_safety_check.py`
(reused as-is for the merge/env-setup logic -- imports `_concat_jsonl` from it
directly, does not reimplement it), but chunks the ONE-OFF temp Chroma index
build to work around the known Chroma `max_batch_size` ceiling
(`chromadb.EphemeralClient().get_max_batch_size()` == 5461 in this repo's
pinned chromadb version).

Why this script exists instead of just using `run_combined_safety_check.py`
directly: `RecipeIndexingService.index_recipes` (app/services/recipe_
indexing_service.py) does a single unchunked `collection.upsert(...)` call
for the whole corpus. Once existing corpus + staged batch exceeds 5461
recipes, that upsert raises, `index_recipes` catches the exception and
silently returns 0 ("indexed=0"), and the benchmark then runs against an
EMPTY temp Chroma collection -- a completely invalid, meaningless result
(not "zero violations", just "retrieval found nothing"). This became
reachable for the first time in this task because the corrected combined
corpus (existing 3,884 + all four staged batches, cross-batch-deduped) is
9,987 recipes total, the first combined-view run in this effort to cross
the ceiling.

This script does NOT touch `app/services/recipe_indexing_service.py` --
the real fix (chunk `index_recipes` itself, or use chromadb's own batching)
is already tracked as a separate BACKLOG item and is deliberately left for
that task. This script only works around the ceiling from the CALLER side,
for this one temp/diagnostic index build, by calling the unmodified
`index_recipes` repeatedly with chunks of the corpus instead of once with
all of it.

Usage:
    python scripts/run_combined_safety_check_chunked.py \\
        --candidate-batch data/processed/candidate_batch_combined_all4_deduped_20260725.jsonl \\
        --runs 3
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_combined_safety_check import _concat_jsonl  # noqa: E402  (reused as-is)

CHUNK_SIZE = 4000  # comfortably under the 5,461 chromadb max_batch_size ceiling


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate-batch", required=True, help="Staged candidate_batch_*.jsonl path")
    parser.add_argument("--candidate-quarantine", default=None, help="Staged candidate quarantine sidecar (optional)")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="Debug: only run the first N benchmark cases")
    parser.add_argument("--keep", action="store_true", help="Don't delete the temp directory afterward")
    args = parser.parse_args()

    from app.config import get_settings

    settings = get_settings()
    seed_path = Path(settings.recipe_path)
    imported_path = seed_path.parent / "imported_recipes.jsonl"
    quarantined_path = seed_path.parent / "quarantined_recipes.jsonl"
    candidate_batch_path = Path(args.candidate_batch)
    candidate_quarantine_path = Path(args.candidate_quarantine) if args.candidate_quarantine else None

    temp_dir = Path(tempfile.mkdtemp(prefix="macrochef_combined_bench_chunked_"))
    temp_chroma = temp_dir / "chroma"
    temp_seed_path = temp_dir / "sample_recipes.jsonl"
    temp_imported_path = temp_dir / "imported_recipes.jsonl"
    temp_quarantined_path = temp_dir / "quarantined_recipes.jsonl"

    print(f"=== Combined-view safety benchmark, CHUNKED INDEX workaround (temp dir: {temp_dir}) ===")
    print(f"Real corpus (READ-ONLY inputs): {seed_path}, {imported_path}, {quarantined_path}")
    print(f"Staged candidate batch: {candidate_batch_path}")
    print("Real data/processed/*.jsonl files and the production Chroma collection are NEVER written to by this script.\n")

    shutil.copyfile(seed_path, temp_seed_path)
    imported_lines = _concat_jsonl([imported_path, candidate_batch_path], temp_imported_path)
    quarantine_sources = [quarantined_path]
    if candidate_quarantine_path is not None:
        quarantine_sources.append(candidate_quarantine_path)
    quarantine_lines = _concat_jsonl(quarantine_sources, temp_quarantined_path)
    print(f"Merged (temp-only) imported corpus: {imported_lines} recipes -> {temp_imported_path}")
    print(f"Merged (temp-only) quarantine sidecar: {quarantine_lines} records -> {temp_quarantined_path}")

    env = os.environ.copy()
    env["RECIPE_DATA_PATH"] = str(temp_seed_path)
    env["CHROMA_PATH"] = str(temp_chroma)

    print(f"\nBuilding a FRESH, temp-only Chroma index at {temp_chroma} in chunks of {CHUNK_SIZE} "
          f"(base corpus only, no user library) -- works around the known chromadb "
          f"max_batch_size=5461 ceiling without touching RecipeIndexingService...")
    index_script = f"""
from app.rag.chroma_client import reset_chroma_collection
from app.services.recipe_indexing_service import RecipeIndexingService

svc = RecipeIndexingService()
recipes = svc._collect_recipes(True, False)
reset_chroma_collection()
chunk_size = {CHUNK_SIZE}
total = 0
for i in range(0, len(recipes), chunk_size):
    total += svc.index_recipes(recipes[i:i + chunk_size])
print(f"indexed={{total}} (of {{len(recipes)}} collected)")
"""
    result = subprocess.run(
        [sys.executable, "-c", index_script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print("--- indexing stderr (for visibility even on success) ---")
        print(result.stderr)
    if result.returncode != 0:
        print("\nABORT: temp index build failed -- see stderr above. Nothing real was touched.")
        if not args.keep:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return 1

    bench_args = [
        sys.executable,
        "scripts/run_safety_benchmark.py",
        "--provider",
        "mock",
        "--runs",
        str(args.runs),
        "--report-path",
        str(temp_dir / "combined_safety_benchmark_report.md"),
        "--cases-json-path",
        str(temp_dir / "combined_safety_benchmark_cases.json"),
    ]
    if args.limit is not None:
        bench_args += ["--limit", str(args.limit)]

    print(f"\nRunning benchmark: {' '.join(bench_args)}\n")
    bench_result = subprocess.run(bench_args, cwd=str(ROOT), env=env)

    print(f"\nTemp dir (report/cases JSON/temp corpus/temp chroma) at: {temp_dir}")
    if not args.keep:
        print("(pass --keep to preserve it for inspection; otherwise it stays as-is for now -- "
              "delete it manually once you've reviewed the report.)")

    return bench_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
