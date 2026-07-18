"""Loads and validates benchmark cases from the per-category JSONL layout in
`app/evaluation/benchmark/cases/`.

One JSONL file per category (see that directory's README.md) so authoring
different categories in parallel never collides on the same file. This
module only assembles/validates `BenchmarkCase` records -- it does not judge
them; the judge is a separate, later component and must stay independent of
`app.services` / `app.utils` (see `case_schema.py`'s module docstring).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.benchmark.case_schema import BenchmarkCase

CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_cases_from_jsonl(path: str | Path) -> list[BenchmarkCase]:
    """Parse one JSONL file into validated BenchmarkCase records.

    Raises pydantic.ValidationError (via BenchmarkCase.model_validate) on any
    malformed case -- callers that want to collect all errors rather than
    fail on the first one should catch per-line instead of calling this
    directly (see scripts/validate_benchmark_cases.py).
    """
    cases_path = Path(path)
    cases: list[BenchmarkCase] = []
    with cases_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{cases_path.name}:{line_number}: invalid JSON ({exc})") from exc
            cases.append(BenchmarkCase.model_validate(payload))
    return cases


def load_all_cases(directory: str | Path | None = None) -> list[BenchmarkCase]:
    """Load every *.jsonl file in the cases directory (sorted for determinism)."""
    cases_dir = Path(directory) if directory is not None else CASES_DIR
    cases: list[BenchmarkCase] = []
    for jsonl_path in sorted(cases_dir.glob("*.jsonl")):
        cases.extend(load_cases_from_jsonl(jsonl_path))
    return cases
