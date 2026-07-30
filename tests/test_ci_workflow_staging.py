"""ROADMAP.md Phase 5, Step 5.3 -- staging auto-deploy wiring in
`.github/workflows/ci.yml`.

This doesn't run the workflow (that needs real Azure credentials/a GitHub
Actions runner) -- it pins the two properties that make this step's design
correct rather than accidentally regressed by a future edit: staging
deploys on an ordinary push to `main` (no `workflow_dispatch` gate, unlike
production), and production's own `preflight`/`build-and-push`/`deploy`
chain stays gated behind `workflow_dispatch` exactly as it was before this
step -- a future edit that accidentally loosens prod's trigger condition
while touching staging's should fail this test, not go unnoticed until a
real merge auto-deploys prod.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CI_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _load_workflow() -> dict:
    with CI_WORKFLOW_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_ci_workflow_is_valid_yaml_with_expected_jobs() -> None:
    workflow = _load_workflow()
    jobs = workflow["jobs"]
    for job_name in (
        "test",
        "web",
        "pgvector-check",
        "staging-deploy",
        "staging-smoke",
        "preflight",
        "build-and-push",
        "deploy",
    ):
        assert job_name in jobs, f"expected job {job_name!r} in ci.yml"


def test_staging_deploy_triggers_on_ordinary_push_to_main_not_workflow_dispatch() -> None:
    """The whole point of this step: staging auto-deploys without a human
    clicking "Run workflow" -- unlike every job in the manual-promote
    chain below it."""
    condition = _load_workflow()["jobs"]["staging-deploy"]["if"]
    assert "github.event_name == 'push'" in condition
    assert "refs/heads/main" in condition
    assert "workflow_dispatch" not in condition
    assert "inputs.deploy" not in condition


def test_staging_smoke_needs_staging_deploy() -> None:
    assert _load_workflow()["jobs"]["staging-smoke"]["needs"] == "staging-deploy"


def test_production_jobs_remain_workflow_dispatch_gated() -> None:
    """Regression guard: this step must never loosen production's own
    human-gate trigger while adding staging's automatic one."""
    jobs = _load_workflow()["jobs"]
    preflight_condition = jobs["preflight"]["if"]
    assert "workflow_dispatch" in preflight_condition
    assert "inputs.deploy" in preflight_condition
    assert jobs["build-and-push"]["needs"] == "preflight"
    assert jobs["deploy"]["needs"] == "build-and-push"


def test_staging_app_name_is_distinct_from_production() -> None:
    env = _load_workflow()["env"]
    assert env["ACA_APP_NAME"] != env["ACA_STAGING_APP_NAME"]
    assert env["ACA_STAGING_APP_NAME"] == "ca-macrochef-staging"


def test_alembic_baseline_maintenance_job_defaults_to_a_no_op() -> None:
    """One-off fix for the ROADMAP 5.1 brownfield-adoption gap (prod's
    schema predates Alembic): this job must never fire on an ordinary
    push/PR, and even on a workflow_dispatch it must stay inert unless the
    operator explicitly picks something other than 'none' -- a future edit
    that flips this default, or drops the explicit `!= 'none'` guard,
    would risk running unattended production-database maintenance on
    every promote."""
    workflow = _load_workflow()
    trigger_key = True if True in workflow else "on"
    alembic_input = workflow[trigger_key]["workflow_dispatch"]["inputs"]["alembic_action"]
    assert alembic_input["default"] == "none"
    assert set(alembic_input["options"]) == {
        "none",
        "inspect",
        "backfill_llm_tables",
        "stamp_0001",
    }

    condition = workflow["jobs"]["alembic-baseline-maintenance"]["if"]
    assert "workflow_dispatch" in condition
    assert "refs/heads/main" in condition
    assert "inputs.alembic_action != 'none'" in condition
