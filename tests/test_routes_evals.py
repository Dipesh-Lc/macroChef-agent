"""HTTP-level tests for `GET /evals/latest` (ROADMAP.md Phase 3, Step 3.4):

- public, no session token required (unlike /admin/llm-usage);
- returns a typed "not generated yet" body (still 200, not a bare 404)
  when data/evaluation/eval_report.json doesn't exist;
- serves the file's contents, validated against `EvalReport`, once it does;
- a corrupt report file surfaces as a loud 502, never a silent 200 of
  garbage or an unhandled 500 stack trace.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.routes_evals as routes_evals_module
from app.main import create_app
from app.schemas.evals import (
    ConstraintSuite,
    EvalReport,
    RetrievalSuite,
    SafetyBenchmarkBucket,
    SafetyBenchmarkSuite,
)


def _make_report() -> EvalReport:
    bucket = SafetyBenchmarkBucket(
        label="inherent (release-blocking)",
        total_cases=269,
        raw_judge_flagged_count=3,
        raw_judge_flagged_rate=0.011,
        wilson_lower=0.0,
        wilson_upper=0.03,
        raw_judge_flagged_case_ids=["subst_005", "subst_006", "subst_009"],
        adjudicated_true_count=0,
        adjudicated_true_case_ids=[],
    )
    non_blocking = SafetyBenchmarkBucket(
        label="precautionary (non-blocking)", total_cases=0, raw_judge_flagged_count=0,
        raw_judge_flagged_rate=0.0, wilson_lower=0.0, wilson_upper=0.0,
    )
    return EvalReport(
        generated_at_utc="2026-07-28T09:00:00+00:00",
        git_commit="deadbeef",
        safety_benchmark=SafetyBenchmarkSuite(
            provider="mock",
            runs=1,
            total_cases=371,
            inherent=bucket,
            precautionary=non_blocking,
            safe_control_over_block=non_blocking,
            release_gate_pass=True,
        ),
        retrieval=RetrievalSuite(skipped=True, skip_reason="Chroma collection empty"),
        constraints=ConstraintSuite(total_recipes=0, profiles=[], sane=True),
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_evals_latest_requires_no_session_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(routes_evals_module, "REPORT_PATH", tmp_path / "eval_report.json")

    response = client.get("/evals/latest")

    assert response.status_code == 200
    # No auth-related 401/403 -- unlike /admin/llm-usage, this route takes
    # no session dependency at all (see this route's module docstring).


def test_evals_latest_returns_not_generated_when_file_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(routes_evals_module, "REPORT_PATH", tmp_path / "eval_report.json")

    response = client.get("/evals/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_generated"
    assert "run_all_evals" in body["message"]


def test_evals_latest_serves_report_contents_once_generated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report_path = tmp_path / "eval_report.json"
    report = _make_report()
    report_path.write_text(report.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(routes_evals_module, "REPORT_PATH", report_path)

    response = client.get("/evals/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["git_commit"] == "deadbeef"
    # Both raw-judge and adjudicated numbers present -- CLAUDE.md's
    # always-both-numbers release-gate rule must survive the HTTP hop.
    assert body["safety_benchmark"]["inherent"]["raw_judge_flagged_count"] == 3
    assert body["safety_benchmark"]["inherent"]["adjudicated_true_count"] == 0
    assert body["safety_benchmark"]["release_gate_pass"] is True
    # Round-trips through the same Pydantic contract the writer used.
    EvalReport.model_validate(body)


def test_evals_latest_returns_502_for_a_corrupt_report_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report_path = tmp_path / "eval_report.json"
    report_path.write_text("{not valid json at all", encoding="utf-8")
    monkeypatch.setattr(routes_evals_module, "REPORT_PATH", report_path)

    response = client.get("/evals/latest")

    assert response.status_code == 502
    assert response.json()["status"] == "corrupt_report"
