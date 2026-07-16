"""Tests for the benchmark case scaffold: schema validators, the loader's
round-trip behavior, and the validator script's quota/contamination logic.

Deliberately does not import from app.services or app.utils, matching the
same independence constraint the scaffold itself observes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.benchmark.case_schema import (
    CATEGORY_ID_PREFIXES,
    BenchmarkCase,
    ConversationTurn,
    SourceCitation,
    StructuredRendering,
)
from app.evaluation.benchmark.loader import CASES_DIR, load_all_cases, load_cases_from_jsonl
from scripts.validate_benchmark_cases import (
    MAX_TOTAL,
    MIN_TOTAL,
    SAFE_CONTROL_MAX_FRACTION,
    SAFE_CONTROL_MIN_FRACTION,
    validate,
)

NON_CONTROL_CATEGORIES = sorted(c for c in CATEGORY_ID_PREFIXES if c != "safe_control")


def _valid_case_kwargs(category: str = "hidden_allergen", suffix: str = "001") -> dict:
    """A minimal, schema-valid case payload for `category`, as a plain dict
    (so tests can mutate a field and assert the resulting ValidationError)."""
    expected_safe = category == "safe_control"
    prefix = CATEGORY_ID_PREFIXES[category]
    payload = {
        "case_id": f"{prefix}_{suffix}",
        "category": category,
        "conversation": [
            {"role": "user", "content": "I'm allergic to peanuts, suggest a dinner."},
            {"role": "assistant", "content": "Here's a peanut-free stir-fry."},
        ],
        "structured_rendering": {
            "allergies": ["peanut"],
            "diet_type": None,
            "typed_ingredients": ["chicken breast", "rice"],
            "inventory_text": None,
            "macro_targets": None,
        },
        "forbidden_terms": [] if expected_safe else ["peanut"],
        "expected_safe": expected_safe,
        "surfaces": ["recommendation_graph"],
        "source_citation": None
        if expected_safe
        else {
            "source": "Example External Authority",
            "url": "https://www.fda.gov/example-allergen-page",
            "quote": "Peanuts are a major food allergen.",
        },
        "pinned_recipe_ids": [],
        "notes": None,
    }
    return payload


# --------------------------------------------------------------------------
# Schema validator rejection paths
# --------------------------------------------------------------------------


def test_valid_non_control_case_constructs() -> None:
    case = BenchmarkCase.model_validate(_valid_case_kwargs("hidden_allergen"))
    assert case.case_id == "hidden_001"
    assert case.forbidden_terms == ["peanut"]


def test_valid_safe_control_case_constructs_without_citation() -> None:
    case = BenchmarkCase.model_validate(_valid_case_kwargs("safe_control"))
    assert case.expected_safe is True
    assert case.forbidden_terms == []
    assert case.source_citation is None


def test_forbidden_terms_must_be_empty_when_expected_safe_true() -> None:
    payload = _valid_case_kwargs("safe_control")
    payload["forbidden_terms"] = ["peanut"]
    with pytest.raises(ValidationError, match="expected_safe=True"):
        BenchmarkCase.model_validate(payload)


def test_forbidden_terms_must_be_non_empty_when_expected_safe_false() -> None:
    payload = _valid_case_kwargs("hidden_allergen")
    payload["forbidden_terms"] = []
    with pytest.raises(ValidationError, match="expected_safe=False"):
        BenchmarkCase.model_validate(payload)


def test_source_citation_required_for_non_control_category() -> None:
    payload = _valid_case_kwargs("hidden_allergen")
    payload["source_citation"] = None
    with pytest.raises(ValidationError, match="requires a source_citation"):
        BenchmarkCase.model_validate(payload)


def test_source_citation_optional_for_safe_control() -> None:
    payload = _valid_case_kwargs("safe_control")
    payload["source_citation"] = {
        "source": "n/a",
        "url": "https://example.org/n-a",
        "quote": "n/a",
    }
    case = BenchmarkCase.model_validate(payload)
    assert case.source_citation is not None


def test_case_id_must_match_category_prefix() -> None:
    payload = _valid_case_kwargs("hidden_allergen")
    payload["case_id"] = "diet_001"
    with pytest.raises(ValidationError, match="must start with"):
        BenchmarkCase.model_validate(payload)


def test_surfaces_must_be_non_empty() -> None:
    payload = _valid_case_kwargs("hidden_allergen")
    payload["surfaces"] = []
    with pytest.raises(ValidationError, match="surfaces must be non-empty"):
        BenchmarkCase.model_validate(payload)


def test_conversation_turn_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        ConversationTurn.model_validate({"role": "system", "content": "x"})


def test_structured_rendering_defaults() -> None:
    rendering = StructuredRendering()
    assert rendering.allergies == []
    assert rendering.typed_ingredients == []
    assert rendering.inventory_text is None
    assert rendering.macro_targets is None


def test_source_citation_requires_all_fields() -> None:
    with pytest.raises(ValidationError):
        SourceCitation.model_validate({"source": "x"})


# --------------------------------------------------------------------------
# Loader round-trip
# --------------------------------------------------------------------------


def test_loader_loads_all_authored_cases_from_real_cases_dir() -> None:
    """The real cases directory grows as authors add cases, so this
    deliberately does not pin an exact count. It asserts the loader
    succeeds against the live directory, every loaded record validates
    against the schema (implicit in `load_all_cases` not raising), the
    count is non-zero, all 9 categories are represented, and the total
    equals the sum of non-blank lines across the category files (a
    self-updating cross-check rather than a hardcoded number)."""
    cases = load_all_cases()

    assert len(cases) > 0
    categories = {case.category for case in cases}
    assert categories == set(CATEGORY_ID_PREFIXES)

    expected_total = 0
    for jsonl_path in CASES_DIR.glob("*.jsonl"):
        with jsonl_path.open("r", encoding="utf-8") as handle:
            expected_total += sum(1 for line in handle if line.strip())
    assert len(cases) == expected_total


def test_loader_round_trips_through_model_dump_json(tmp_path: Path) -> None:
    original = BenchmarkCase.model_validate(_valid_case_kwargs("morphology"))
    path = tmp_path / "morphology.jsonl"
    path.write_text(original.model_dump_json() + "\n", encoding="utf-8")

    loaded = load_cases_from_jsonl(path)

    assert len(loaded) == 1
    assert loaded[0] == original


def test_loader_skips_blank_lines(tmp_path: Path) -> None:
    original = BenchmarkCase.model_validate(_valid_case_kwargs("diet_trap"))
    path = tmp_path / "diet_trap.jsonl"
    path.write_text(f"\n{original.model_dump_json()}\n\n", encoding="utf-8")

    loaded = load_cases_from_jsonl(path)

    assert loaded == [original]


def test_loader_raises_on_invalid_json_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text("{not valid json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_cases_from_jsonl(path)


# --------------------------------------------------------------------------
# Validator script: quota / duplicate / contamination logic
# --------------------------------------------------------------------------


def _write_cases(directory: Path, category: str, cases: list[dict]) -> None:
    path = directory / f"{category}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case) + "\n")


def _build_balanced_case_set(total: int, safe_fraction: float) -> dict[str, list[dict]]:
    """Builds a full 9-category case set with `total` cases split so
    safe_control is exactly `safe_fraction` of the total (rounded) and the
    remaining 8 categories share the rest as evenly as possible."""
    safe_count = round(total * safe_fraction)
    remaining = total - safe_count
    per_category = remaining // len(NON_CONTROL_CATEGORIES)
    leftover = remaining - per_category * len(NON_CONTROL_CATEGORIES)

    by_category: dict[str, list[dict]] = {}
    by_category["safe_control"] = [
        _valid_case_kwargs("safe_control", suffix=f"{i:03d}") for i in range(safe_count)
    ]
    for index, category in enumerate(NON_CONTROL_CATEGORIES):
        count = per_category + (1 if index < leftover else 0)
        by_category[category] = [
            _valid_case_kwargs(category, suffix=f"{i:03d}") for i in range(count)
        ]
    return by_category


def test_validate_passes_on_a_well_formed_full_size_case_set(tmp_path: Path) -> None:
    total = 320
    safe_fraction = 0.175  # within [15%, 20%]
    by_category = _build_balanced_case_set(total, safe_fraction)
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is True, "\n".join(report)
    assert any("RESULT: PASS" in line for line in report)


def test_validate_fails_when_total_too_low(tmp_path: Path) -> None:
    by_category = _build_balanced_case_set(18, 0.175)
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[QUOTA FAIL]" in line and "total case count" in line for line in report)


def test_validate_fails_when_total_too_high(tmp_path: Path) -> None:
    by_category = _build_balanced_case_set(MAX_TOTAL + 20, 0.175)
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[QUOTA FAIL]" in line and "total case count" in line for line in report)


def test_validate_fails_when_safe_control_fraction_too_low(tmp_path: Path) -> None:
    total = 320
    by_category = _build_balanced_case_set(total, 0.05)  # well below 15%
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[QUOTA FAIL]" in line and "safe_control" in line for line in report)


def test_validate_fails_when_safe_control_fraction_too_high(tmp_path: Path) -> None:
    total = 320
    by_category = _build_balanced_case_set(total, 0.35)  # well above 20%
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[QUOTA FAIL]" in line and "safe_control" in line for line in report)


def test_validate_fails_when_a_category_is_missing(tmp_path: Path) -> None:
    total = 320
    by_category = _build_balanced_case_set(total, 0.175)
    del by_category["morphology"]  # drop one category entirely
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[QUOTA FAIL]" in line and "morphology" in line for line in report)


def test_validate_detects_duplicate_case_ids(tmp_path: Path) -> None:
    total = 320
    by_category = _build_balanced_case_set(total, 0.175)
    # Force a duplicate within diet_trap's own file (case_id must still
    # match its category prefix, so duplicate within the same category).
    by_category["diet_trap"][0]["case_id"] = by_category["diet_trap"][1]["case_id"]
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[DUPLICATE FAIL]" in line for line in report)


def test_validate_flags_empty_citation_url_as_contamination(tmp_path: Path) -> None:
    total = 320
    by_category = _build_balanced_case_set(total, 0.175)
    by_category["hidden_allergen"][0]["source_citation"]["url"] = ""
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[CONTAMINATION FAIL]" in line for line in report)


def test_validate_flags_self_referential_citation_url_as_contamination(tmp_path: Path) -> None:
    total = 320
    by_category = _build_balanced_case_set(total, 0.175)
    by_category["hidden_allergen"][0]["source_citation"]["url"] = (
        "https://github.com/dipesh-lc/macrochef-agent/blob/main/app/services/constraint_engine.py"
    )
    for category, cases in by_category.items():
        _write_cases(tmp_path, category, cases)

    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("[CONTAMINATION FAIL]" in line for line in report)


def test_validate_reports_no_files_found(tmp_path: Path) -> None:
    ok, report = validate(cases_dir=tmp_path)

    assert ok is False
    assert any("No *.jsonl files found" in line for line in report)


def test_scaffold_examples_directory_is_the_default_cases_dir() -> None:
    assert CASES_DIR.exists()
    assert list(CASES_DIR.glob("*.jsonl")), "expected the 9 scaffold example files to exist"


def test_min_max_total_and_safe_control_fraction_constants_are_sane() -> None:
    assert MIN_TOTAL == 300
    assert MAX_TOTAL == 500
    assert math.isclose(SAFE_CONTROL_MIN_FRACTION, 0.15)
    assert math.isclose(SAFE_CONTROL_MAX_FRACTION, 0.20)
