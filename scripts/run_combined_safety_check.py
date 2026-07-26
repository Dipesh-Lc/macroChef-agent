"""Run the existing adversarial safety benchmark against a COMBINED VIEW of
the live corpus + a staged candidate batch (2026-07-25 corpus-expansion task,
Step 5) -- WITHOUT ever writing to, reindexing, or otherwise touching the
real `data/processed/*.jsonl` files or the production Chroma collection at
`settings.chroma_path`.

How: builds a throwaway temp directory containing (a) the unmodified 25
curated seeds, (b) a MERGED COPY of `imported_recipes.jsonl` + the given
staged candidate batch file, and (c) a fresh, temp-only Chroma collection
built from that merged copy -- then runs `scripts/run_safety_benchmark.py`
(mock provider, free) with `RECIPE_DATA_PATH`/`CHROMA_PATH` env vars pointed
at that temp directory. The real corpus files and the real Chroma
collection are read-only inputs (the seed/imported files are only ever
copied, never opened for writing) and are never touched.

Only `include_base=True, include_user=False` recipes are indexed/loaded --
this deliberately never touches the per-user recipe library / any live DB
connection.

Usage:
    python scripts/run_combined_safety_check.py \\
        --candidate-batch data/processed/candidate_batch_20260725.jsonl \\
        --runs 1
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


def _concat_jsonl(paths: list[Path], dest: Path) -> int:
    """Concatenate the JSONL lines of every path in `paths` that exists into
    `dest` (created fresh). Returns the number of lines written. No
    parsing/validation -- every input is already a valid Recipe/quarantine
    JSONL line produced by an earlier, already-validated pipeline stage."""
    count = 0
    with dest.open("w", encoding="utf-8") as out:
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        out.write(line if line.endswith("\n") else line + "\n")
                        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate-batch", required=True, help="Staged candidate_batch_*.jsonl path")
    parser.add_argument("--candidate-quarantine", default=None, help="Staged candidate quarantine sidecar (optional)")
    parser.add_argument("--runs", type=int, default=1, help="k for the benchmark's k-run methodology (default 1 here for speed; the officially-scored run uses 3)")
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

    temp_dir = Path(tempfile.mkdtemp(prefix="macrochef_combined_bench_"))
    temp_chroma = temp_dir / "chroma"
    temp_seed_path = temp_dir / "sample_recipes.jsonl"
    temp_imported_path = temp_dir / "imported_recipes.jsonl"
    temp_quarantined_path = temp_dir / "quarantined_recipes.jsonl"

    print(f"=== Combined-view safety benchmark (temp dir: {temp_dir}) ===")
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

    print(f"\nBuilding a FRESH, temp-only Chroma index at {temp_chroma} (base corpus only, no user library)...")
    index_script = (
        "from app.services.recipe_indexing_service import RecipeIndexingService;"
        "n = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=False);"
        "print(f'indexed={n}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", index_script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
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
