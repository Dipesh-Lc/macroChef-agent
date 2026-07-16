"""Validates the adversarial safety benchmark case set in
`app/evaluation/benchmark/cases/*.jsonl` against the `BenchmarkCase` schema
and the quota/contamination rules that make the set trustworthy as a gate.

This is a scaffold-time and (eventually) CI-time gate, not a judge -- it
never runs a recipe recommendation or scores an allergy violation. It only
checks that the case *set itself* is well-formed:

1. Every JSONL line parses and validates against `BenchmarkCase`
   (`app.evaluation.benchmark.case_schema`) -- malformed cases are reported
   with file/line context, not silently skipped.
2. QUOTA CHECKS:
   - total case count is in [300, 500].
   - `safe_control` is between 15% and 20% of the total. This is a hard
     requirement: without a real block of safe controls, a system that
     refuses every request would score a perfect 0% violation rate for the
     wrong reason (never actually serving anything), and that failure mode
     would be invisible without safe controls to catch it.
   - every category in `case_schema.CaseCategory` has at least one case.
3. Duplicate `case_id` detection across all files combined.
4. CONTAMINATION HEURISTIC: flags any case whose `source_citation.url` is
   empty, or whose citation plausibly points back at this repository
   (relative/local paths, `file://`, or a URL naming this repo/package)
   instead of an external authority. Ground truth must be traceable to
   something outside the implementation under test -- see
   `app/evaluation/benchmark/cases/README.md`.

Exits nonzero on ANY failure (missing quota, duplicate id, contamination
hit, or schema error) so this can be wired into CI later as a hard gate.

Deliberately does NOT import from `app.services` or `app.utils` -- this
validator checks the case set's own internal consistency, not agreement
with the constraint engine under test.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from app.evaluation.benchmark.case_schema import (  # noqa: E402
    CATEGORY_ID_PREFIXES,
    SAFE_CONTROL_CATEGORY,
    BenchmarkCase,
)
from app.evaluation.benchmark.loader import CASES_DIR, load_cases_from_jsonl  # noqa: E402

MIN_TOTAL = 300
MAX_TOTAL = 500
SAFE_CONTROL_MIN_FRACTION = 0.15
SAFE_CONTROL_MAX_FRACTION = 0.20

ALL_CATEGORIES = set(CATEGORY_ID_PREFIXES)

# Markers that suggest a citation URL points back into this repository
# (or is otherwise not an independent external authority) rather than out
# to a real external source. Deliberately conservative/string-based --
# false positives here just mean a human double-checks a fine citation,
# false negatives would let contamination slip through silently.
_REPO_URL_MARKERS = (
    "macrochef",
    "localhost",
    "127.0.0.1",
    "file://",
    "github.com/dipesh-lc",
)


def _citation_contamination_reason(case: BenchmarkCase) -> str | None:
    """Returns a human-readable reason if `case`'s citation looks
    contaminated (self-referential or missing), else None. Only meaningful
    for non-control cases; safe_control cases may have no citation at all
    and that is not itself contamination."""
    citation = case.source_citation
    if case.category == SAFE_CONTROL_CATEGORY and citation is None:
        return None
    if citation is None:
        # Schema validation already rejects this for non-control cases, but
        # guard here too in case this function is ever called on
        # already-invalid data.
        return "missing source_citation for a non-control case"
    url = (citation.url or "").strip()
    if not url:
        return "empty source_citation.url"
    lowered = url.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return f"source_citation.url is not an external http(s) URL: {url!r}"
    for marker in _REPO_URL_MARKERS:
        if marker in lowered:
            return f"source_citation.url looks self-referential (matched {marker!r}): {url!r}"
    return None


def _load_all_cases_reporting_errors(cases_dir: Path) -> tuple[list[BenchmarkCase], list[str]]:
    """Loads every *.jsonl file in cases_dir, collecting schema errors
    instead of raising on the first one, so a single validation run reports
    every problem at once."""
    cases: list[BenchmarkCase] = []
    errors: list[str] = []
    jsonl_paths = sorted(cases_dir.glob("*.jsonl"))
    if not jsonl_paths:
        errors.append(f"No *.jsonl files found in {cases_dir}")
        return cases, errors

    for path in jsonl_paths:
        try:
            cases.extend(load_cases_from_jsonl(path))
        except ValidationError as exc:
            errors.append(f"{path.name}: schema validation failed:\n{exc}")
        except ValueError as exc:
            errors.append(str(exc))
    return cases, errors


def validate(cases_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Runs every check and returns (ok, report_lines)."""
    cases_dir = cases_dir if cases_dir is not None else CASES_DIR
    report: list[str] = []
    ok = True

    cases, load_errors = _load_all_cases_reporting_errors(cases_dir)
    for error in load_errors:
        report.append(f"[SCHEMA ERROR] {error}")
        ok = False

    total = len(cases)
    by_category: Counter[str] = Counter(case.category for case in cases)

    report.append(f"Total cases loaded: {total}")
    for category in sorted(ALL_CATEGORIES):
        report.append(f"  {category}: {by_category.get(category, 0)}")

    # --- Quota check: total count -----------------------------------
    if not (MIN_TOTAL <= total <= MAX_TOTAL):
        report.append(
            f"[QUOTA FAIL] total case count {total} is outside the required "
            f"range [{MIN_TOTAL}, {MAX_TOTAL}]"
        )
        ok = False
    else:
        report.append(f"[QUOTA OK] total case count {total} is within [{MIN_TOTAL}, {MAX_TOTAL}]")

    # --- Quota check: every category non-empty -----------------------
    missing_categories = sorted(ALL_CATEGORIES - set(by_category))
    if missing_categories:
        report.append(f"[QUOTA FAIL] categories with zero cases: {missing_categories}")
        ok = False
    else:
        report.append("[QUOTA OK] every category has at least one case")

    # --- Quota check: safe_control fraction ---------------------------
    safe_count = by_category.get(SAFE_CONTROL_CATEGORY, 0)
    if total == 0:
        report.append("[QUOTA FAIL] safe_control fraction cannot be checked: total case count is 0")
        ok = False
    else:
        fraction = safe_count / total
        if not (SAFE_CONTROL_MIN_FRACTION <= fraction <= SAFE_CONTROL_MAX_FRACTION):
            report.append(
                f"[QUOTA FAIL] safe_control is {fraction:.1%} of total "
                f"({safe_count}/{total}), required "
                f"[{SAFE_CONTROL_MIN_FRACTION:.0%}, {SAFE_CONTROL_MAX_FRACTION:.0%}]"
            )
            ok = False
        else:
            report.append(
                f"[QUOTA OK] safe_control is {fraction:.1%} of total "
                f"({safe_count}/{total}), within "
                f"[{SAFE_CONTROL_MIN_FRACTION:.0%}, {SAFE_CONTROL_MAX_FRACTION:.0%}]"
            )

    # --- Duplicate case_id detection ----------------------------------
    id_counts = Counter(case.case_id for case in cases)
    duplicates = sorted(case_id for case_id, count in id_counts.items() if count > 1)
    if duplicates:
        report.append(f"[DUPLICATE FAIL] duplicate case_id values: {duplicates}")
        ok = False
    else:
        report.append("[DUPLICATE OK] no duplicate case_id values")

    # --- Contamination heuristic ---------------------------------------
    contamination_hits: list[str] = []
    for case in cases:
        reason = _citation_contamination_reason(case)
        if reason is not None:
            contamination_hits.append(f"{case.case_id}: {reason}")
    if contamination_hits:
        report.append("[CONTAMINATION FAIL] suspect source citations:")
        for hit in contamination_hits:
            report.append(f"  - {hit}")
        ok = False
    else:
        report.append("[CONTAMINATION OK] no suspect source citations found")

    report.append("")
    report.append(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return ok, report


def main() -> int:
    ok, report = validate()
    print("\n".join(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
