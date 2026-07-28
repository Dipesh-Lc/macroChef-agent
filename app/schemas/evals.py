"""Contracts for the evals system (ROADMAP.md Phase 3, Step 3.4): a single
stable `data/evaluation/eval_report.json`, written by
`scripts/run_all_evals.py` and served read-only by `GET /evals/latest`
(`app.api.routes_evals`). A future frontend eval page (ROADMAP Step 4.6)
consumes this same shape.

MONEY GATE: nothing that produces an `EvalReport` today ever spends real
provider money -- see `scripts/run_all_evals.py`'s module docstring. The
safety-benchmark suite always runs against the mock/deterministic
provider; `SafetyBenchmarkSuite.provider` is always `"mock"` for anything
this repo's own tooling writes.

RELEASE-GATE SEMANTICS (CLAUDE.md, human-decided 2026-07-17, agents may not
amend): "The raw judge-flagged count is always published alongside the
adjudicated number... the judge is never modified to close the gap."
`SafetyBenchmarkBucket` carries `raw_judge_flagged_*` and
`adjudicated_true_*` as separate, always-both-present fields for exactly
this reason -- never collapse them into one pass/fail number.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SafetyBenchmarkBucket(BaseModel):
    """One scored bucket from a `scripts/run_safety_benchmark.py` run
    (`inherent`, `precautionary`, or `safe_control_over_block`).

    `raw_judge_flagged_*` is `app.evaluation.benchmark.safety_judge`'s own
    count -- a deliberately recall-biased substring matcher, kept
    structurally unable to import the code it grades. It is the "judge"
    half of CLAUDE.md's always-both-numbers rule.

    `adjudicated_true_*` is the exhaustive mechanical re-check
    (`scripts/verify_benchmark_evidence.py`) that runs the REAL
    `contains_allergen`/`violates_diet_type` production functions directly
    against every judge-flagged case's served ingredients -- the
    "adjudicated" half. It is only computed for the release-blocking
    `inherent` bucket (see `SafetyBenchmarkSuite.release_gate_pass`'s
    docstring for why `precautionary`/`safe_control_over_block` leave this
    `None`): those two buckets are explicitly non-blocking per CLAUDE.md's
    release-gate semantics, and adjudicating them would imply a gate that
    does not exist.
    """

    label: str
    total_cases: int
    raw_judge_flagged_count: int
    raw_judge_flagged_rate: float
    wilson_lower: float
    wilson_upper: float
    raw_judge_flagged_case_ids: list[str] = Field(default_factory=list)
    adjudicated_true_count: int | None = None
    adjudicated_true_case_ids: list[str] | None = None


class SafetyBenchmarkCategoryBreakdown(BaseModel):
    """Per-category (hidden_allergen, prompt_injection, morphology, ...)
    counts from the same worst run used for the `inherent` bucket above.
    Reference/display data for a future frontend eval page -- never itself
    a gate."""

    category: str
    total_cases: int
    raw_judge_flagged_count: int


class SafetyBenchmarkSuite(BaseModel):
    provider: str
    runs: int
    total_cases: int
    inherent: SafetyBenchmarkBucket
    precautionary: SafetyBenchmarkBucket
    safe_control_over_block: SafetyBenchmarkBucket
    category_breakdown: list[SafetyBenchmarkCategoryBreakdown] = Field(default_factory=list)
    # True iff `inherent.adjudicated_true_count == 0` -- the ONLY
    # release-blocking condition per CLAUDE.md's release-gate semantics.
    # precautionary/safe_control_over_block never affect this flag.
    release_gate_pass: bool


class RetrievalCategoryResult(BaseModel):
    category: str
    gated: bool
    semantic_mrr: float
    keyword_mrr: float
    hybrid_mrr: float
    semantic_recall_at_10: float
    keyword_recall_at_10: float
    hybrid_recall_at_10: float
    # None for non-gated (reference-only) categories.
    win: bool | None = None


class RetrievalSuite(BaseModel):
    """See `app.evaluation.eval_retrieval` / `scripts/evaluate_retrieval.py`
    for the full methodology. `skipped` is True when the Chroma collection
    hasn't been built (e.g. a bare checkout with no baked index) -- this is
    NOT a failure, just "nothing to score yet"."""

    skipped: bool
    skip_reason: str | None = None
    query_count: int = 0
    gate_pass: bool | None = None
    categories: list[RetrievalCategoryResult] = Field(default_factory=list)


class ConstraintProfileResult(BaseModel):
    """One profile's pass over the corpus via
    `app.evaluation.eval_constraints.evaluate_constraint_set` (a thin
    wrapper over the real `constraint_engine.validate_recipe`). This is a
    coverage/smoke snapshot, not a graded correctness metric -- there is no
    external ground truth for "how many corpus recipes should a peanut
    allergy reject"; the sanity check below instead watches for the two
    shapes that would indicate a real bug: an unrestricted profile
    rejecting anything, or a restrictive profile rejecting nothing."""

    label: str
    allergies: list[str]
    diet_type: str | None
    total_recipes: int
    valid: int
    rejected: int


class ConstraintSuite(BaseModel):
    total_recipes: int
    profiles: list[ConstraintProfileResult]
    # False if the no-restriction baseline rejected anything, or any
    # restrictive profile rejected nothing -- see ConstraintProfileResult's
    # docstring.
    sane: bool


class EvalReport(BaseModel):
    generated_at_utc: str
    git_commit: str
    safety_benchmark: SafetyBenchmarkSuite
    retrieval: RetrievalSuite
    constraints: ConstraintSuite
    # A handful of headline numbers vs. the PREVIOUS eval_report.json (if
    # one existed at write time) -- e.g. did the release gate flip, did the
    # adjudicated-true count change. Never a full recursive diff.
    deltas_vs_previous: dict[str, float | int | bool | str | None] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class EvalReportNotAvailable(BaseModel):
    """`GET /evals/latest`'s response when `data/evaluation/eval_report.json`
    has not been generated yet (e.g. a fresh checkout before anyone has run
    `scripts/run_all_evals.py`) -- an honest, typed "not yet" response
    instead of a bare 404 with no body."""

    status: str = "not_generated"
    message: str = (
        "No eval report has been generated yet. Run `python scripts/run_all_evals.py` "
        "to produce data/evaluation/eval_report.json."
    )
