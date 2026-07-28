"""`GET /evals/latest` (ROADMAP.md Phase 3, Step 3.4): serves the committed
`data/evaluation/eval_report.json` -- public, read-only, no session
dependency (mirrors `app.api.routes_health`'s unauthenticated pattern, not
`app.api.routes_admin`'s session-gated one: this is meant for a public
frontend eval page, ROADMAP Step 4.6, and for anyone reading the repo).

This endpoint never runs an eval itself -- it only reads whatever
`scripts/run_all_evals.py` last wrote to disk. Regenerating the report is
a deliberate, out-of-band action (a script run, wired into CI as a gate
step -- see `.github/workflows/ci.yml`), never a side effect of a GET
request.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.evals import EvalReport, EvalReportNotAvailable

router = APIRouter(prefix="/evals", tags=["evals"])

# Repo-root-relative -- matches scripts/run_all_evals.py's own
# `_default_report_path()` (ROOT / "data" / "evaluation" / "eval_report.json").
REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "eval_report.json"


@router.get("/latest", response_model=EvalReport)
def get_latest_eval_report() -> EvalReport | JSONResponse:
    """Returns the current `eval_report.json` contents, or a typed
    "not generated yet" body (still HTTP 200 -- this is an expected,
    ordinary state for a fresh checkout, not an error) if the file is
    absent. A malformed/corrupt file is the one case that surfaces as a
    502: it means something upstream (a bad `scripts/run_all_evals.py`
    write) is broken, which IS worth surfacing loudly rather than masking
    as "not generated"."""
    if not REPORT_PATH.exists():
        return JSONResponse(status_code=200, content=EvalReportNotAvailable().model_dump())

    try:
        return EvalReport.model_validate_json(REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - a corrupt file must not raise a raw 500
        return JSONResponse(
            status_code=502,
            content={
                "status": "corrupt_report",
                "message": (
                    f"data/evaluation/eval_report.json exists but could not be parsed: {exc}"
                ),
            },
        )
