"""Tests for scripts/run_all_evals.py (ROADMAP.md Phase 3, Step 3.4):
report shape (both raw-judge and adjudicated-true numbers present for the
safety suite, per CLAUDE.md's release-gate semantics), the retrieval-gate
reimplementation, the constraint smoke suite's sanity check, the
read-before-write delta against a previous report, and a mutation
self-check proving the whole pipeline (real graph + real adjudication)
actually catches a planted safety fault -- the permanent regression
version of this task's "prove the CI gate works" experiment (see this
task's own report for the one-off CLI-level demonstration of the same
thing against the actual CI gate command).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_all_evals as run_all_evals  # noqa: E402
import scripts.run_safety_benchmark as safety_mod  # noqa: E402
from app.evaluation.benchmark.loader import load_all_cases  # noqa: E402
from app.schemas.evals import (  # noqa: E402
    ConstraintProfileResult,
    ConstraintSuite,
    EvalReport,
    RetrievalSuite,
    SafetyBenchmarkBucket,
    SafetyBenchmarkSuite,
)
from app.schemas.recommendation import ValidationResult  # noqa: E402


def _admit_everything(recipe, profile) -> ValidationResult:  # noqa: ARG001 - must match validate_recipe's signature
    return ValidationResult(is_valid=True)


def _make_bucket(
    label: str, *, n: int = 0, successes: int = 0, adjudicated_true_count: int | None = None
) -> SafetyBenchmarkBucket:
    return SafetyBenchmarkBucket(
        label=label,
        total_cases=n,
        raw_judge_flagged_count=successes,
        raw_judge_flagged_rate=(successes / n) if n else 0.0,
        wilson_lower=0.0,
        wilson_upper=0.0,
        adjudicated_true_count=adjudicated_true_count,
    )


def _make_safety_suite(*, release_gate_pass: bool) -> SafetyBenchmarkSuite:
    # raw_judge_flagged_count == 1 even when release_gate_pass is True --
    # deliberately mirrors real-world reality (the judge has known false
    # positives; adjudicated_true_count is what actually decides the gate).
    adjudicated = 0 if release_gate_pass else 1
    return SafetyBenchmarkSuite(
        provider="mock",
        runs=1,
        total_cases=10,
        inherent=_make_bucket(
            "inherent (release-blocking)", n=10, successes=1, adjudicated_true_count=adjudicated
        ),
        precautionary=_make_bucket("precautionary (non-blocking)"),
        safe_control_over_block=_make_bucket("safe_control over-blocking (non-blocking)"),
        release_gate_pass=release_gate_pass,
    )


# ---------------------------------------------------------------------------
# Report shape: real (small) safety-suite run -- both raw and adjudicated
# numbers present, per CLAUDE.md's always-both-numbers release-gate rule.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def small_safety_suite() -> SafetyBenchmarkSuite:
    # Deliberately small (--safety-limit-equivalent) so this fixture (shared
    # by every test below that needs a real run) stays fast: the frozen
    # cases are loaded/sorted by category file, so the first N cases below
    # are all real, previously-scored `derivative_name` cases.
    return run_all_evals.run_safety_suite(runs=1, limit=12, cases_dir=None)


def test_safety_suite_inherent_bucket_carries_both_raw_and_adjudicated_numbers(
    small_safety_suite: SafetyBenchmarkSuite,
) -> None:
    inherent = small_safety_suite.inherent
    assert inherent.adjudicated_true_count is not None
    assert inherent.adjudicated_true_case_ids is not None
    assert inherent.raw_judge_flagged_count >= inherent.adjudicated_true_count
    # This is the frozen, already-verified-clean case set (0/269 as of
    # commit 0840e60) -- a small prefix of it must also be clean.
    assert inherent.adjudicated_true_count == 0
    assert small_safety_suite.release_gate_pass is True


def test_safety_suite_non_inherent_buckets_never_carry_an_adjudicated_number(
    small_safety_suite: SafetyBenchmarkSuite,
) -> None:
    """precautionary/safe_control_over_block are explicitly non-blocking per
    CLAUDE.md's release-gate semantics -- adjudicating them would imply a
    gate that does not exist, so these must stay None, never 0 (0 would
    read as "adjudicated and clean", a false claim about scope)."""
    assert small_safety_suite.precautionary.adjudicated_true_count is None
    assert small_safety_suite.precautionary.adjudicated_true_case_ids is None
    assert small_safety_suite.safe_control_over_block.adjudicated_true_count is None
    assert small_safety_suite.safe_control_over_block.adjudicated_true_case_ids is None


def test_safety_suite_category_breakdown_is_nonempty_and_sums_to_total(
    small_safety_suite: SafetyBenchmarkSuite,
) -> None:
    breakdown = small_safety_suite.category_breakdown
    assert breakdown
    assert sum(entry.total_cases for entry in breakdown) == small_safety_suite.total_cases
    for entry in breakdown:
        assert entry.raw_judge_flagged_count <= entry.total_cases


# ---------------------------------------------------------------------------
# Mutation self-check: proves the ENTIRE pipeline built in this task --
# real graph run -> judge -> build_case_evidence_bundle ->
# verify_benchmark_evidence.verify() -> adjudicated_true_count -- actually
# detects a planted safety fault, not just that the number happens to be
# zero today. Mirrors tests/test_run_safety_benchmark.py's existing
# mutation self-check pattern (same fault, same morphology-inherent
# case selection), extended to also prove the ADJUDICATION layer this
# task added reacts to it.
# ---------------------------------------------------------------------------


def test_mutation_self_check_adjudicated_bucket_catches_a_planted_safety_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.graph.nodes as nodes

    cases = load_all_cases()
    morphology_inherent = [
        case for case in cases if case.category == "morphology" and not case.expected_safe
    ][:6]
    assert len(morphology_inherent) == 6

    baseline_outcomes = safety_mod.run_all_cases(morphology_inherent, run_index=0)
    baseline_count, baseline_ids = run_all_evals._adjudicate_inherent_bucket(
        morphology_inherent, [baseline_outcomes]
    )

    monkeypatch.setattr(nodes, "validate_recipe", _admit_everything)
    monkeypatch.setattr(safety_mod.constraint_engine, "validate_recipe", _admit_everything)

    faulted_outcomes = safety_mod.run_all_cases(morphology_inherent, run_index=1)
    faulted_count, faulted_ids = run_all_evals._adjudicate_inherent_bucket(
        morphology_inherent, [faulted_outcomes]
    )

    newly_caught = set(faulted_ids) - set(baseline_ids)
    assert newly_caught, (
        "Mutation self-check FAILED (vacuous): faulting constraint_engine.validate_recipe "
        "to admit everything did not cause the adjudicator "
        "(scripts/verify_benchmark_evidence.verify, called from "
        "scripts/run_all_evals._adjudicate_inherent_bucket) to newly flag ANY morphology "
        f"inherent case beyond the baseline (baseline adjudicated-true: {sorted(baseline_ids)}). "
        "Do not trust this suite's release_gate_pass until this is fixed."
    )
    assert faulted_count > baseline_count

    # And the suite-level flag this feeds actually flips, end to end.
    report = safety_mod.build_report(
        morphology_inherent, [faulted_outcomes], provider_label="mock"
    )
    suite = SafetyBenchmarkSuite(
        provider="mock",
        runs=1,
        total_cases=len(morphology_inherent),
        inherent=run_all_evals._bucket_to_schema(
            report.inherent,
            adjudicated_true_count=faulted_count,
            adjudicated_true_case_ids=faulted_ids,
        ),
        precautionary=run_all_evals._bucket_to_schema(report.precautionary),
        safe_control_over_block=run_all_evals._bucket_to_schema(report.safe_control_over_block),
        release_gate_pass=(faulted_count == 0),
    )
    assert suite.release_gate_pass is False


# ---------------------------------------------------------------------------
# Constraint smoke suite
# ---------------------------------------------------------------------------


def test_constraint_suite_baseline_clean_and_restrictive_profiles_reject_something() -> None:
    suite = run_all_evals.run_constraint_suite()

    baseline = suite.profiles[0]
    assert baseline.label == "no_restrictions"
    assert baseline.rejected == 0
    assert baseline.valid == suite.total_recipes

    for profile in suite.profiles[1:]:
        assert profile.rejected > 0, f"{profile.label} rejected nothing -- filter may be a no-op"

    assert suite.sane is True


def test_constraint_suite_flags_insane_when_baseline_rejects_something(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for the sanity check itself: if the no-restriction
    baseline profile starts rejecting recipes (a real bug shape -- e.g. a
    stray filter applied even with no allergies/diet set), `sane` must flip
    to False, not silently stay True."""
    import app.evaluation.eval_constraints as eval_constraints_module

    def _reject_everything(recipe, profile):
        return ValidationResult(is_valid=False, rejection_reason="planted fault")

    monkeypatch.setattr(eval_constraints_module, "validate_recipe", _reject_everything)

    suite = run_all_evals.run_constraint_suite()
    assert suite.sane is False


# ---------------------------------------------------------------------------
# Retrieval suite: skip path + gate reimplementation (synthetic, fast --
# no vector-store/corpus I/O)
# ---------------------------------------------------------------------------


class _FakeVectorStoreCount:
    """Stand-in for `app.rag.vector_store.VectorStore` (ROADMAP 5.2) --
    only `.count()` matters to `run_retrieval_suite`'s empty-store skip
    check."""

    def __init__(self, count: int):
        self._count = count

    def count(self) -> int:
        return self._count


def test_retrieval_suite_skips_when_vector_store_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_all_evals, "get_vector_store", lambda: _FakeVectorStoreCount(0))

    suite = run_all_evals.run_retrieval_suite()

    assert suite.skipped is True
    assert suite.gate_pass is None
    assert suite.categories == []
    assert "empty" in (suite.skip_reason or "")


def _fake_run_retrieval_eval_result(*, dish_semantic_wins: bool, dietary_present: bool) -> dict:
    """Builds a synthetic run_retrieval_eval()-shaped result with exactly
    the fields `_category_aggregate` reads (recall@5/10, ndcg@5/10, mrr)
    for one query each in `dish` and (optionally) `dietary`."""

    def _row(
        query_id: str, category: str, semantic_mrr: float, keyword_mrr: float, hybrid_mrr: float
    ) -> dict:
        def _metrics(mrr: float) -> dict:
            return {"recall@5": mrr, "recall@10": mrr, "ndcg@5": mrr, "ndcg@10": mrr, "mrr": mrr}

        return {
            "query_id": query_id,
            "category": category,
            "num_relevant": 1,
            "semantic": _metrics(semantic_mrr),
            "keyword": _metrics(keyword_mrr),
            "hybrid": _metrics(hybrid_mrr),
        }

    dish_semantic_mrr = 1.0 if dish_semantic_wins else 0.0
    dish_keyword_mrr = 0.0 if dish_semantic_wins else 1.0
    per_query = [
        _row("dish_01", "dish", dish_semantic_mrr, dish_keyword_mrr, 0.9),
    ]
    if dietary_present:
        per_query.append(_row("dietary_01", "dietary", 1.0, 0.0, 0.9))
    return {"per_query": per_query, "aggregate": {}, "k_values": [5, 10]}


def test_retrieval_suite_gate_pass_true_when_semantic_wins_both_gated_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_all_evals, "get_vector_store", lambda: _FakeVectorStoreCount(100))
    monkeypatch.setattr(run_all_evals, "load_eval_queries", lambda: [])
    monkeypatch.setattr(
        run_all_evals,
        "run_retrieval_eval",
        lambda *a, **k: _fake_run_retrieval_eval_result(
            dish_semantic_wins=True, dietary_present=True
        ),
    )

    suite = run_all_evals.run_retrieval_suite()

    assert suite.skipped is False
    assert suite.gate_pass is True
    dish = next(c for c in suite.categories if c.category == "dish")
    assert dish.gated is True
    assert dish.win is True


def test_retrieval_suite_gate_pass_false_when_semantic_loses_a_gated_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_all_evals, "get_vector_store", lambda: _FakeVectorStoreCount(100))
    monkeypatch.setattr(run_all_evals, "load_eval_queries", lambda: [])
    monkeypatch.setattr(
        run_all_evals,
        "run_retrieval_eval",
        lambda *a, **k: _fake_run_retrieval_eval_result(
            dish_semantic_wins=False, dietary_present=True
        ),
    )

    suite = run_all_evals.run_retrieval_suite()

    assert suite.gate_pass is False
    dish = next(c for c in suite.categories if c.category == "dish")
    assert dish.win is False


def test_retrieval_suite_gate_is_non_vacuous_when_a_gated_category_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing 'dietary' entirely must FAIL the gate, not vacuously pass it
    (mirrors scripts/evaluate_retrieval.py's own non-vacuous-gate rule)."""
    monkeypatch.setattr(run_all_evals, "get_vector_store", lambda: _FakeVectorStoreCount(100))
    monkeypatch.setattr(run_all_evals, "load_eval_queries", lambda: [])
    monkeypatch.setattr(
        run_all_evals,
        "run_retrieval_eval",
        lambda *a, **k: _fake_run_retrieval_eval_result(
            dish_semantic_wins=True, dietary_present=False
        ),
    )

    suite = run_all_evals.run_retrieval_suite()

    assert suite.gate_pass is False


# ---------------------------------------------------------------------------
# Read-before-write delta against a previous report
# ---------------------------------------------------------------------------


def test_compute_deltas_returns_empty_dict_when_no_previous_report(tmp_path: Path) -> None:
    report_path = tmp_path / "eval_report.json"
    current = EvalReport(
        generated_at_utc="2026-07-28T00:00:00+00:00",
        git_commit="abc123",
        safety_benchmark=_make_safety_suite(release_gate_pass=True),
        retrieval=RetrievalSuite(skipped=True, skip_reason="test"),
        constraints=ConstraintSuite(total_recipes=0, profiles=[], sane=True),
    )

    deltas = run_all_evals._compute_deltas(report_path, current)

    assert deltas == {}


def test_compute_deltas_flags_release_gate_flip_and_count_deltas(tmp_path: Path) -> None:
    report_path = tmp_path / "eval_report.json"
    previous = EvalReport(
        generated_at_utc="2026-07-27T00:00:00+00:00",
        git_commit="prev123",
        safety_benchmark=_make_safety_suite(release_gate_pass=True),
        retrieval=RetrievalSuite(skipped=True, skip_reason="test"),
        constraints=ConstraintSuite(total_recipes=0, profiles=[], sane=True),
    )
    report_path.write_text(previous.model_dump_json(), encoding="utf-8")

    current = EvalReport(
        generated_at_utc="2026-07-28T00:00:00+00:00",
        git_commit="cur456",
        safety_benchmark=_make_safety_suite(release_gate_pass=False),
        retrieval=RetrievalSuite(skipped=True, skip_reason="test"),
        constraints=ConstraintSuite(total_recipes=0, profiles=[], sane=True),
    )

    deltas = run_all_evals._compute_deltas(report_path, current)

    assert deltas["release_gate_pass_changed"] is True
    assert deltas["inherent_adjudicated_true_count_delta"] == 1
    assert deltas["previous_generated_at_utc"] == "2026-07-27T00:00:00+00:00"


def test_compute_deltas_survives_a_corrupt_previous_report(tmp_path: Path) -> None:
    report_path = tmp_path / "eval_report.json"
    report_path.write_text("{not valid json", encoding="utf-8")
    current = EvalReport(
        generated_at_utc="2026-07-28T00:00:00+00:00",
        git_commit="abc123",
        safety_benchmark=_make_safety_suite(release_gate_pass=True),
        retrieval=RetrievalSuite(skipped=True, skip_reason="test"),
        constraints=ConstraintSuite(total_recipes=0, profiles=[], sane=True),
    )

    deltas = run_all_evals._compute_deltas(report_path, current)

    assert "previous_report_unreadable" in deltas


# ---------------------------------------------------------------------------
# main(): orchestration + exit code, with fast fakes for the three suites
# (the suites' own real behavior is covered above/elsewhere -- this only
# tests main()'s glue: file writing, stable path, exit-code gating).
# ---------------------------------------------------------------------------


def _stub_safety_suite(monkeypatch: pytest.MonkeyPatch, *, release_gate_pass: bool) -> None:
    def _stub(**kwargs):
        return _make_safety_suite(release_gate_pass=release_gate_pass)

    monkeypatch.setattr(run_all_evals, "run_safety_suite", _stub)


def _stub_retrieval_suite_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_all_evals, "run_retrieval_suite", lambda: RetrievalSuite(skipped=True, skip_reason="t")
    )


def test_main_writes_stable_report_path_and_returns_zero_when_gate_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_safety_suite(monkeypatch, release_gate_pass=True)
    _stub_retrieval_suite_skipped(monkeypatch)
    clean_profile = ConstraintProfileResult(
        label="x", allergies=[], diet_type=None, total_recipes=1, valid=1, rejected=0
    )
    monkeypatch.setattr(
        run_all_evals,
        "run_constraint_suite",
        lambda: ConstraintSuite(total_recipes=1, profiles=[clean_profile], sane=True),
    )

    report_path = tmp_path / "eval_report.json"
    exit_code = run_all_evals.main(["--report-path", str(report_path)])

    assert exit_code == 0
    assert report_path.exists()
    written = EvalReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert written.safety_benchmark.release_gate_pass is True


def test_main_returns_nonzero_exit_code_when_release_gate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_safety_suite(monkeypatch, release_gate_pass=False)
    _stub_retrieval_suite_skipped(monkeypatch)
    monkeypatch.setattr(
        run_all_evals,
        "run_constraint_suite",
        lambda: ConstraintSuite(total_recipes=0, profiles=[], sane=True),
    )

    report_path = tmp_path / "eval_report.json"
    exit_code = run_all_evals.main(["--report-path", str(report_path)])

    assert exit_code == 1
    written = EvalReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert written.safety_benchmark.release_gate_pass is False


def test_main_skip_flags_produce_placeholder_suites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_safety_suite(monkeypatch, release_gate_pass=True)

    report_path = tmp_path / "eval_report.json"
    exit_code = run_all_evals.main(
        ["--report-path", str(report_path), "--skip-retrieval", "--skip-constraints"]
    )

    assert exit_code == 0
    written = EvalReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert written.retrieval.skipped is True
    assert written.constraints.profiles == []
    assert any("skip" in note.lower() for note in written.notes)


# ---------------------------------------------------------------------------
# Money gate: importing this module must never leave a real provider
# configured, mirroring scripts/run_safety_benchmark.py's own test.
# ---------------------------------------------------------------------------


def test_importing_run_all_evals_forces_mock_provider_env() -> None:
    import os

    assert os.environ.get("MODEL_PROVIDER") == "mock"
    assert os.environ.get("MODEL_PROVIDER_FALLBACKS") == "mock"
    provider_keys = (
        "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_KEY"
    )
    for key in provider_keys:
        assert key not in os.environ

    # This script offers no CLI path back to a real provider at all --
    # unlike scripts/run_safety_benchmark.py, there is no --provider flag.
    parser = run_all_evals.build_arg_parser()
    args = parser.parse_args([])
    assert not hasattr(args, "provider")
    assert not hasattr(args, "confirm_real_provider_spend")


def test_eval_report_schema_rejects_unknown_shape() -> None:
    """Cheap smoke test that EvalReport is actually a validating Pydantic
    contract, not a loose dict -- a missing required field must raise."""
    with pytest.raises(PydanticValidationError):
        EvalReport.model_validate({"generated_at_utc": "x"})
