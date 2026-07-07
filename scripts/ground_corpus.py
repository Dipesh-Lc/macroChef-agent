"""Compute USDA-grounded macros for the recipe corpus and report tag-vs-computed drift.

Idempotent: re-running overwrites data/processed/grounding.jsonl from scratch
(sorted by recipe_id) -- re-runs never double-write or drift. USDA lookups
are served from the on-disk FdcCache (data/cache/fdc_cache.json) after the
first run, so a re-run only re-fetches ingredients that changed.

Never writes to sample_recipes.jsonl or imported_recipes.jsonl -- the
self-reported tag macros there stay untouched, which is what makes the
tag-vs-computed comparison in the report meaningful.

Usage:
    python scripts/ground_corpus.py [--sidecar-path PATH] [--report-path PATH]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.grounding_job import render_report, run_grounding  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar-path", default="data/processed/grounding.jsonl")
    parser.add_argument("--report-path", default="data/processed/grounding_report.md")
    args = parser.parse_args()

    report = run_grounding(sidecar_path=args.sidecar_path)
    markdown = render_report(report)

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"\nWrote sidecar to {args.sidecar_path}")
    print(f"Wrote report to {args.report_path}")


if __name__ == "__main__":
    main()
