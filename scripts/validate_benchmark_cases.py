"""Validates the adversarial safety benchmark case set in
`app/evaluation/benchmark/cases/*.jsonl` against the `BenchmarkCase` schema
and the quota/contamination rules that make the set trustworthy as a gate.

This is a scaffold-time and (eventually) CI-time gate, not a judge -- it
never runs a recipe recommendation or scores an allergy violation. It only
checks that the case *set itself* is well-formed:

1. Every JSONL line parses and validates against `BenchmarkCase`
   (`app.evaluation.benchmark.case_schema`) -- malformed cases are reported
   with file/line context, not silently skipped. Validation happens per
   *line* (not per file): one invalid case does not hide the report for
   every other case in the same file, which matters while `claim_strength`
   labeling (see check 5) is still landing incrementally.
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
5. CLAIM_STRENGTH: `BenchmarkCase` requires `claim_strength` ("inherent" or
   "precautionary") on every case with `expected_safe: false` -- i.e. every
   case that actually asserts a forbidden-term claim -- and forbids it
   otherwise (schema-enforced -- see `case_schema.py`; keyed on
   `expected_safe`, not category, so a non-`safe_control` case that itself
   asserts zero forbidden terms is correctly counted as having no claim to
   classify). This script additionally reports the
   inherent/precautionary/no_claim/unlabeled split per category, computed
   from the raw JSON (not the validated model), so the split is visible
   even while some cases in a category are still missing the field.
6. DUPLICATE PAYLOAD: flags any two cases whose `(conversation,
   structured_rendering)` pair is byte-identical, even if `case_id` and
   other metadata differ. The pre-freeze review found `prompt_injection`
   had 40 case_ids but only 14 distinct payloads -- 26 were clones that
   silently 5x-multiplied one template's outcome into the denominator.
7. ALLERGY VOCABULARY: flags any `structured_rendering.allergies` entry
   that isn't in a documented, closed set of expected labels, to catch a
   typo (e.g. "treenuts") that would otherwise silently produce a vacuous
   case. Both singular and plural spellings are allowed for terms a real
   user could type either way -- see `ALLOWED_ALLERGY_LABELS` below for why
   this is not the same thing as forbidding plurals.

Exits nonzero on ANY failure (missing quota, duplicate id, contamination
hit, schema error, duplicate payload, or unknown allergy label) so this can
be wired into CI later as a hard gate.

Deliberately does NOT import from `app.services` or `app.utils` -- this
validator checks the case set's own internal consistency, not agreement
with the constraint engine under test. `ALLOWED_ALLERGY_LABELS` below is a
hardcoded mirror of the allergen vocabulary for that reason: importing
`app.services.constraint_engine.ALLERGEN_ALIASES` would make this check
agree with the implementation under test by construction, which is exactly
the tautology this benchmark is designed to avoid (see case_schema.py's
module docstring and cases/README.md's blind-authoring rule).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
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
from app.evaluation.benchmark.loader import CASES_DIR  # noqa: E402

MIN_TOTAL = 300
MAX_TOTAL = 500
SAFE_CONTROL_MIN_FRACTION = 0.15
SAFE_CONTROL_MAX_FRACTION = 0.20

ALL_CATEGORIES = set(CATEGORY_ID_PREFIXES)
NON_CONTROL_CATEGORIES = ALL_CATEGORIES - {SAFE_CONTROL_CATEGORY}

# Closed set of allergy labels a `structured_rendering.allergies` entry may
# use. Mirrors `app.services.constraint_engine.ALLERGEN_ALIASES`'s public
# keys by hand (not by import -- see module docstring), plus explicit plural
# forms.
#
# Both "tree nut" and "tree nuts" are listed deliberately, not by oversight:
# `UserProfile.allergies` is free-text (`list[str]`, no dropdown -- see
# `StructuredRendering`'s docstring in case_schema.py), so a real user could
# type either. Verified by execution: "tree nuts" is not itself an alias
# key, but `app.utils.ingredient_normalizer.normalize_ingredient`
# depluralizes it to "tree nut" before alias lookup, so it still blocks
# correctly -- it is not a vacuous label. This set exists to catch
# typos/unknown labels (e.g. "treenuts", "nutt"), not to forbid legitimate
# plurals; extend it (both forms) if a case set legitimately needs a label
# not yet listed here.
ALLOWED_ALLERGY_LABELS = frozenset(
    {
        "dairy",
        "milk",
        "egg",
        "eggs",
        "peanut",
        "peanuts",
        "tree nut",
        "tree nuts",
        "nuts",
        "wheat",
        "gluten",
        "soy",
        "soya",
        "shellfish",
        "crustacean",
        "fish",
        "seafood",
        "sesame",
    }
)

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


def _load_all_cases_reporting_errors(
    cases_dir: Path,
) -> tuple[list[BenchmarkCase], list[dict], list[str]]:
    """Loads every *.jsonl file in cases_dir, validating line-by-line and
    collecting every error instead of raising (or discarding a whole file)
    on the first one, so a single validation run reports every problem at
    once.

    Returns `(cases, raw_records, errors)`:
    - `cases`: every line that parsed as JSON *and* validated against
      `BenchmarkCase`.
    - `raw_records`: every line that parsed as JSON, regardless of whether
      it validated against `BenchmarkCase`. Checks that must keep working
      while some cases are individually invalid (the claim_strength split,
      duplicate-payload detection, allergy vocabulary) read from this list
      instead of `cases`, so one bad case doesn't blind those checks to
      every other case in its file.
    - `errors`: human-readable, file:line-scoped problem descriptions.
    """
    cases: list[BenchmarkCase] = []
    raw_records: list[dict] = []
    errors: list[str] = []
    jsonl_paths = sorted(cases_dir.glob("*.jsonl"))
    if not jsonl_paths:
        errors.append(f"No *.jsonl files found in {cases_dir}")
        return cases, raw_records, errors

    for path in jsonl_paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path.name}:{line_number}: invalid JSON ({exc})")
                    continue
                if isinstance(payload, dict):
                    raw_records.append(payload)
                try:
                    cases.append(BenchmarkCase.model_validate(payload))
                except ValidationError as exc:
                    case_id = payload.get("case_id", "<unknown case_id>") if isinstance(payload, dict) else "<non-object line>"
                    errors.append(
                        f"{path.name}:{line_number} ({case_id}): schema validation failed:\n{exc}"
                    )
    return cases, raw_records, errors


def _payload_fingerprint(record: dict) -> str:
    """A canonical string of just `conversation` + `structured_rendering`,
    for duplicate-payload detection. Deliberately excludes case_id,
    category, surfaces, and notes -- two cases with the identical adversarial
    content but different bookkeeping metadata are still the "same case"
    for the purposes of this check (that's exactly the clone pattern the
    pre-freeze review found in prompt_injection)."""
    return json.dumps(
        {
            "conversation": record.get("conversation"),
            "structured_rendering": record.get("structured_rendering"),
        },
        sort_keys=True,
    )


def _duplicate_payload_groups(raw_records: list[dict]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for record in raw_records:
        case_id = record.get("case_id", "<unknown case_id>")
        groups[_payload_fingerprint(record)].append(case_id)
    return {key: ids for key, ids in groups.items() if len(ids) > 1}


def _unknown_allergy_label_hits(raw_records: list[dict]) -> list[str]:
    hits: list[str] = []
    for record in raw_records:
        case_id = record.get("case_id", "<unknown case_id>")
        rendering = record.get("structured_rendering") or {}
        for label in rendering.get("allergies") or []:
            normalized = str(label).strip().lower()
            if normalized not in ALLOWED_ALLERGY_LABELS:
                hits.append(f"{case_id}: unexpected allergy label {label!r}")
    return hits


def _claim_strength_split_report(raw_records: list[dict]) -> list[str]:
    """Per-category inherent/precautionary/unlabeled/no-claim counts, computed
    from raw JSON so the split is visible even for categories that are still
    mid-labeling (and therefore failing full schema validation) -- see
    check 5 in the module docstring.

    Partitions on `expected_safe`, not category (advisor pre-freeze review,
    item 1): a case has a forbidden-term claim to classify iff
    `expected_safe` is False, regardless of category. A non-safe_control
    case with `expected_safe: true` (e.g. a morphology case confirming a
    lookalike name is NOT the allergen) has no claim at all and must show up
    as "no_claim", not silently default into "inherent" -- keying on category
    instead of expected_safe is exactly the bug this report existed to avoid
    surfacing."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for record in raw_records:
        category = record.get("category")
        if category not in ALL_CATEGORIES:
            continue
        expected_safe = record.get("expected_safe")
        claim = record.get("claim_strength")
        if expected_safe is True:
            bucket = "no_claim" if claim is None else "unlabeled/invalid"
        elif expected_safe is False:
            bucket = claim if claim in ("inherent", "precautionary") else "unlabeled/invalid"
        else:
            bucket = "unlabeled/invalid"
        counts[category][bucket] += 1

    lines = ["claim_strength split per category, partitioned on expected_safe "
             "(release-blocking violation rate is computed over 'inherent' only; "
             "'precautionary' is a separate, non-blocking number; 'no_claim' is "
             "expected_safe=True cases with no forbidden-term claim to classify "
             "-- see README.md):"]
    for category in sorted(ALL_CATEGORIES):
        category_counts = counts.get(category, Counter())
        inherent = category_counts.get("inherent", 0)
        precautionary = category_counts.get("precautionary", 0)
        no_claim = category_counts.get("no_claim", 0)
        unlabeled = category_counts.get("unlabeled/invalid", 0)
        lines.append(
            f"  {category}: inherent={inherent} precautionary={precautionary} "
            f"no_claim={no_claim} unlabeled/invalid={unlabeled}"
        )
    return lines


def validate(cases_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Runs every check and returns (ok, report_lines)."""
    cases_dir = cases_dir if cases_dir is not None else CASES_DIR
    report: list[str] = []
    ok = True

    cases, raw_records, load_errors = _load_all_cases_reporting_errors(cases_dir)
    for error in load_errors:
        report.append(f"[SCHEMA ERROR] {error}")
        ok = False

    total = len(cases)
    by_category: Counter[str] = Counter(case.category for case in cases)

    report.append(f"Total cases loaded (schema-valid): {total}")
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

    # --- Duplicate payload detection (item 2 support) -------------------
    duplicate_payload_groups = _duplicate_payload_groups(raw_records)
    if duplicate_payload_groups:
        report.append(
            "[DUPLICATE PAYLOAD FAIL] cases with byte-identical "
            "(conversation, structured_rendering):"
        )
        for case_ids in duplicate_payload_groups.values():
            report.append(f"  - {sorted(case_ids)}")
        ok = False
    else:
        report.append(
            "[DUPLICATE PAYLOAD OK] no two cases share an identical "
            "(conversation, structured_rendering) payload"
        )

    # --- Allergy vocabulary check (item 3 support) -----------------------
    unknown_allergy_hits = _unknown_allergy_label_hits(raw_records)
    if unknown_allergy_hits:
        report.append(
            "[ALLERGY VOCAB FAIL] structured_rendering.allergies label(s) "
            f"not in the documented closed set ({sorted(ALLOWED_ALLERGY_LABELS)}):"
        )
        for hit in unknown_allergy_hits:
            report.append(f"  - {hit}")
        ok = False
    else:
        report.append("[ALLERGY VOCAB OK] every allergy label is in the documented closed set")

    # --- claim_strength split report (item 4) ---------------------------
    report.append("")
    report.extend(_claim_strength_split_report(raw_records))

    report.append("")
    report.append(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return ok, report


def main() -> int:
    ok, report = validate()
    print("\n".join(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
