"""Runs every eval suite MacroChef has (safety benchmark, retrieval,
constraint smoke) and writes one stable, committed-shape report:
`data/evaluation/eval_report.json` (ROADMAP.md Phase 3, Step 3.4).

MONEY GATE (hard constraint -- read before touching this file): this
script NEVER offers a real-provider path. There is no `--provider` flag
here at all. The block immediately below forces `MODEL_PROVIDER=mock` /
`MODEL_PROVIDER_FALLBACKS=mock` and strips every provider API key from the
environment before any `app.*` import happens (mirrors
`scripts/run_safety_benchmark.py`'s own money gate, which this script also
imports and therefore gets a second, redundant copy of -- defense in
depth, not decoration). The only way to score MacroChef against a REAL
judge/provider is `scripts/run_safety_benchmark.py --provider real
--confirm-real-provider-spend`, run BY A HUMAN, directly -- this script
does not wrap or expose that path, on purpose, so "run all the evals" can
never accidentally become "spend money". See CLAUDE.md's money human-gate
and this task's own spec.

RELEASE-GATE SEMANTICS (CLAUDE.md, human-decided 2026-07-17, not amendable
by agents): the raw judge-flagged count and the adjudicated-true count are
ALWAYS published together, never collapsed into one pass/fail number. This
script computes both for the release-blocking `inherent` bucket:

- raw judge-flagged: `app.evaluation.benchmark.safety_judge`'s own count,
  from a live `scripts/run_safety_benchmark.py`-style run against the
  mock/deterministic provider.
- adjudicated-true: `scripts/verify_benchmark_evidence.py`'s exhaustive
  mechanical re-check, which runs the REAL `contains_allergen`/
  `violates_diet_type` production functions directly against every
  judge-flagged case's served ingredients. This is what actually gates
  `release_gate_pass` -- see `app.schemas.evals.SafetyBenchmarkSuite`.

WHY `--safety-runs` DEFAULTS TO 1, NOT THE OFFICIAL k=3: the pre-registered
any-run-worst-case-of-3 methodology exists to guard against a NON-
deterministic scorer (a real LLM judge/provider has response variance).
The mock/deterministic provider this script always uses has none --
MacroChef's own code path (retrieval, constraint_engine, mock provider)
is deterministic given fixed inputs, so re-running the same 371 cases
against it three times reproduces the same outcome three times (confirmed
empirically during this task: see this task's own report). Paying 3x the
wall-clock for identical numbers would work directly against this step's
"keep it fast" requirement. `--safety-runs` stays an explicit flag (not
hardcoded) so a human can still reproduce the OFFICIAL k=3 report via this
script if they want to; the officially-scored, CLAUDE.md-referenced number
continues to come from `scripts/run_safety_benchmark.py`'s own default
(k=3), run directly -- this script's number is a fast regression signal,
not a replacement for that release-gate artifact.

NIGHTLY REAL-JUDGE RUN: intentionally NOT wired here or in CI. Per
CLAUDE.md's money human-gate, a full judge run needs a cost estimate +
explicit human approval first. See `docs/HUMAN_INPUTS.md` for the
placeholder entry describing what that would take to turn on.

Usage:
    python scripts/run_all_evals.py
    python scripts/run_all_evals.py --report-path /tmp/eval_report.json
    python scripts/run_all_evals.py --safety-limit 20  # fast dev iteration only
"""

from __future__ import annotations

# --- MONEY GATE: forced-mock safety default (see module docstring) --------
import os

_FORCED_MOCK_ENV_KEYS = (
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
)
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["MODEL_PROVIDER_FALLBACKS"] = "mock"
for _key in _FORCED_MOCK_ENV_KEYS:
    os.environ.pop(_key, None)

# --- Ordinary imports -------------------------------------------------------

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# `scripts/` has no `__init__.py` -- it is picked up as an implicit
# namespace package (Python 3 native, no marker file needed) once ROOT is
# on sys.path, which is what lets the two `from scripts...` imports below
# resolve. See this task's report for why cross-script imports (rather
# than subprocess) were chosen: it gives direct access to each script's
# already-built result objects (BenchmarkReport, evidence bundle, retrieval
# gate booleans) instead of re-parsing rendered text output.

from app.evaluation.eval_constraints import evaluate_constraint_set  # noqa: E402
from app.evaluation.eval_retrieval import load_eval_queries, run_retrieval_eval  # noqa: E402
from app.rag.loaders import load_corpus  # noqa: E402
from app.rag.vector_store import get_vector_store  # noqa: E402
from app.schemas.evals import (  # noqa: E402
    ConstraintProfileResult,
    ConstraintSuite,
    EvalReport,
    RetrievalCategoryResult,
    RetrievalSuite,
    SafetyBenchmarkBucket,
    SafetyBenchmarkCategoryBreakdown,
    SafetyBenchmarkSuite,
)
from app.schemas.user import UserProfile  # noqa: E402
from scripts import evaluate_retrieval as retrieval_gate_module  # noqa: E402
from scripts import run_safety_benchmark as safety_mod  # noqa: E402
from scripts import verify_benchmark_evidence as verify_mod  # noqa: E402

# ---------------------------------------------------------------------------
# Safety benchmark suite
# ---------------------------------------------------------------------------


def _bucket_to_schema(
    bucket: safety_mod.BucketResult,
    *,
    adjudicated_true_count: int | None = None,
    adjudicated_true_case_ids: list[str] | None = None,
) -> SafetyBenchmarkBucket:
    return SafetyBenchmarkBucket(
        label=bucket.label,
        total_cases=bucket.worst_n,
        raw_judge_flagged_count=bucket.worst_successes,
        raw_judge_flagged_rate=bucket.worst_rate,
        wilson_lower=bucket.wilson_lower,
        wilson_upper=bucket.wilson_upper,
        raw_judge_flagged_case_ids=bucket.worst_run_case_ids,
        adjudicated_true_count=adjudicated_true_count,
        adjudicated_true_case_ids=adjudicated_true_case_ids,
    )


def _adjudicate_inherent_bucket(
    cases: list, per_run_outcomes: list[list[safety_mod.CaseOutcome]]
) -> tuple[int, list[str]]:
    """Runs `scripts/verify_benchmark_evidence.py`'s exhaustive mechanical
    adjudication against the `inherent`-only slice of this run's evidence
    bundle. Returns (distinct case_id count, sorted case_ids) of cases
    where the REAL `contains_allergen`/`violates_diet_type` production
    functions found a genuine violation -- the "adjudicated-true" half of
    CLAUDE.md's always-both-numbers rule.

    Writes the filtered evidence bundle to a throwaway temp file because
    `verify_benchmark_evidence.verify()`'s public contract is a file path
    (matching its CLI usage, which stays the source of truth for a human
    re-running an adjudication by hand) -- not reshaped here, to avoid two
    diverging entry points into the same frozen verifier.
    """
    full_bundle = safety_mod.build_case_evidence_bundle(cases, per_run_outcomes)
    inherent_bundle = [entry for entry in full_bundle if entry["claim_strength"] == "inherent"]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(inherent_bundle, handle)
        temp_path = handle.name

    try:
        violations = verify_mod.verify(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)

    distinct_case_ids = sorted({violation[0] for violation in violations})
    return len(distinct_case_ids), distinct_case_ids


def _category_breakdown(
    cases: list, per_run_outcomes: list[list[safety_mod.CaseOutcome]], worst_run_index: int
) -> list[SafetyBenchmarkCategoryBreakdown]:
    """Per-category counts from the SAME run used to score the `inherent`
    bucket (see `BucketResult.worst_run_index`) -- reference data for a
    future frontend eval page, never itself a gate."""
    outcomes = per_run_outcomes[worst_run_index]
    by_category: dict[str, list[safety_mod.CaseOutcome]] = {}
    for outcome in outcomes:
        by_category.setdefault(outcome.category, []).append(outcome)

    breakdown = []
    for category in sorted(by_category):
        category_outcomes = by_category[category]
        flagged = sum(1 for o in category_outcomes if o.violated)
        breakdown.append(
            SafetyBenchmarkCategoryBreakdown(
                category=category,
                total_cases=len(category_outcomes),
                raw_judge_flagged_count=flagged,
            )
        )
    return breakdown


def run_safety_suite(
    *, runs: int, limit: int | None, cases_dir: str | None
) -> SafetyBenchmarkSuite:
    # Same fix as scripts/run_safety_benchmark.py's main() -- this function
    # (like that script) calls `run_recommendation_graph` directly, bypassing
    # `app.main.create_app()`'s lifespan (the only place `init_db()` normally
    # runs). Without this, a fresh sqlite file (fresh checkout / fresh CI
    # runner) makes `recipe_retriever_node` 500 with "no such table" on every
    # case, which is caught and silently recorded as "0 recipes served" --
    # a false-negative gate, not a real one. Idempotent, safe to call every
    # time. See that script's own fix for the full incident writeup.
    from app.data.db import init_db

    init_db()

    cases = safety_mod.load_all_cases(cases_dir) if cases_dir else safety_mod.load_all_cases()
    if limit is not None:
        cases = cases[:limit]

    per_run_outcomes = [safety_mod.run_all_cases(cases, run_index) for run_index in range(runs)]
    report = safety_mod.build_report(cases, per_run_outcomes, provider_label="mock")

    adjudicated_count, adjudicated_case_ids = _adjudicate_inherent_bucket(cases, per_run_outcomes)

    inherent = _bucket_to_schema(
        report.inherent,
        adjudicated_true_count=adjudicated_count,
        adjudicated_true_case_ids=adjudicated_case_ids,
    )
    precautionary = _bucket_to_schema(report.precautionary)
    safe_control_over_block = _bucket_to_schema(report.safe_control_over_block)

    return SafetyBenchmarkSuite(
        provider="mock",
        runs=runs,
        total_cases=len(cases),
        inherent=inherent,
        precautionary=precautionary,
        safe_control_over_block=safe_control_over_block,
        category_breakdown=_category_breakdown(
            cases, per_run_outcomes, report.inherent.worst_run_index
        ),
        # The ONLY release-blocking condition (CLAUDE.md release-gate
        # semantics): zero ADJUDICATED-true inherent violations. Never
        # gated on the raw judge-flagged count, and never on
        # precautionary/safe_control_over_block.
        release_gate_pass=(adjudicated_count == 0),
    )


# ---------------------------------------------------------------------------
# Retrieval suite
# ---------------------------------------------------------------------------


def run_retrieval_suite() -> RetrievalSuite:
    if get_vector_store().count() == 0:
        return RetrievalSuite(
            skipped=True,
            skip_reason=(
                "Vector store is empty (data/chroma is not baked in this checkout -- "
                "it's built at Docker image build time / by scripts/ingest_recipes.py, and "
                "is gitignored). Semantic and hybrid scores would be meaningless zeros, so "
                "this suite is skipped rather than reported as a false regression."
            ),
        )

    queries = load_eval_queries()
    k_values = [5, 10]
    result = run_retrieval_eval(queries, k_values=k_values)

    by_category: dict[str, list[dict]] = {}
    for row in result["per_query"]:
        by_category.setdefault(row["category"], []).append(row)

    metric_order = [f"recall@{k}" for k in k_values] + [f"ndcg@{k}" for k in k_values] + ["mrr"]
    categories: list[RetrievalCategoryResult] = []
    gate_results: list[bool] = []
    for category in sorted(by_category):
        rows = by_category[category]
        agg = retrieval_gate_module._category_aggregate(rows, metric_order)
        gated = category in retrieval_gate_module.GATED_CATEGORIES

        win: bool | None = None
        if gated:
            # Mirrors scripts/evaluate_retrieval.py's `_run_gate` condition
            # (i): semantic strictly beats keyword on BOTH MRR and
            # Recall@10. Reimplemented here (not imported) because
            # `_run_gate` is print-oriented and scores every gated category
            # jointly; this needs one category's boolean in isolation.
            win = (
                agg["semantic"]["mrr"] > agg["keyword"]["mrr"]
                and agg["semantic"]["recall@10"] > agg["keyword"]["recall@10"]
            )
            best_mrr = max(agg["semantic"]["mrr"], agg["keyword"]["mrr"])
            tolerance = retrieval_gate_module.HYBRID_MRR_TOLERANCE
            hybrid_ok = agg["hybrid"]["mrr"] >= best_mrr - tolerance
            gate_results.append(win and hybrid_ok)

        categories.append(
            RetrievalCategoryResult(
                category=category,
                gated=gated,
                semantic_mrr=agg["semantic"]["mrr"],
                keyword_mrr=agg["keyword"]["mrr"],
                hybrid_mrr=agg["hybrid"]["mrr"],
                semantic_recall_at_10=agg["semantic"]["recall@10"],
                keyword_recall_at_10=agg["keyword"]["recall@10"],
                hybrid_recall_at_10=agg["hybrid"]["recall@10"],
                win=win,
            )
        )

    # Non-vacuous gate (matches scripts/evaluate_retrieval.py's own rule):
    # both GATED_CATEGORIES must actually be present, or this is a FAIL,
    # not a vacuous PASS.
    present_gated = {c.category for c in categories if c.gated}
    gate_pass = present_gated == set(retrieval_gate_module.GATED_CATEGORIES) and all(gate_results)

    return RetrievalSuite(
        skipped=False,
        query_count=len(queries),
        gate_pass=gate_pass,
        categories=categories,
    )


# ---------------------------------------------------------------------------
# Constraint smoke suite
# ---------------------------------------------------------------------------

# A small, representative battery of profiles over the real allergen/diet
# vocabulary `app.services.constraint_engine.ALLERGEN_ALIASES` /
# `app.schemas.user.SUPPORTED_DIET_TYPES` actually enforce -- not
# exhaustive (that's the safety benchmark's job), just enough spread to
# catch the two bug shapes described in `ConstraintProfileResult`'s
# docstring: an unrestricted profile rejecting anything, or a restrictive
# profile rejecting nothing.
_CONSTRAINT_PROFILES: list[tuple[str, list[str], str | None]] = [
    ("no_restrictions", [], None),
    ("peanut_allergy", ["peanut"], None),
    ("dairy_allergy", ["dairy"], None),
    ("gluten_free_diet", [], "gluten-free"),
    ("vegan_diet", [], "vegan"),
    ("shellfish_fish_allergy", ["shellfish", "fish"], None),
    ("multi_constraint", ["peanut", "dairy", "egg"], "vegetarian"),
]


def run_constraint_suite() -> ConstraintSuite:
    recipes = load_corpus()
    profiles: list[ConstraintProfileResult] = []
    for label, allergies, diet_type in _CONSTRAINT_PROFILES:
        profile = UserProfile(allergies=allergies, diet_type=diet_type)
        counts = evaluate_constraint_set(recipes, profile)
        profiles.append(
            ConstraintProfileResult(
                label=label,
                allergies=allergies,
                diet_type=diet_type,
                total_recipes=len(recipes),
                valid=counts["valid"],
                rejected=counts["rejected"],
            )
        )

    baseline = profiles[0]
    restrictive = profiles[1:]
    sane = baseline.rejected == 0 and all(p.rejected > 0 for p in restrictive)

    return ConstraintSuite(total_recipes=len(recipes), profiles=profiles, sane=sane)


# ---------------------------------------------------------------------------
# Report assembly: read-before-write delta against the previous report
# ---------------------------------------------------------------------------


DeltaValue = float | int | bool | str | None


def _compute_deltas(report_path: Path, current: EvalReport) -> dict[str, DeltaValue]:
    """Read-before-write diff against whatever currently sits at
    `report_path` (if anything) -- this is intentionally a small, named set
    of headline numbers, not a generic recursive JSON diff."""
    if not report_path.exists():
        return {}
    try:
        previous = EvalReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - a corrupt/old-shape file must not crash a new run
        return {"previous_report_unreadable": str(exc)}

    prev_safety = previous.safety_benchmark
    cur_safety = current.safety_benchmark
    cur_flagged = cur_safety.inherent.raw_judge_flagged_count
    prev_flagged = prev_safety.inherent.raw_judge_flagged_count
    cur_adjudicated = cur_safety.inherent.adjudicated_true_count or 0
    prev_adjudicated = prev_safety.inherent.adjudicated_true_count or 0
    deltas: dict[str, DeltaValue] = {
        "previous_generated_at_utc": previous.generated_at_utc,
        "inherent_raw_judge_flagged_count_delta": cur_flagged - prev_flagged,
        "inherent_adjudicated_true_count_delta": cur_adjudicated - prev_adjudicated,
        "release_gate_pass_changed": cur_safety.release_gate_pass != prev_safety.release_gate_pass,
        "retrieval_gate_pass_changed": current.retrieval.gate_pass != previous.retrieval.gate_pass,
        "constraints_sane_changed": current.constraints.sane != previous.constraints.sane,
    }
    return deltas


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Where to write the report (default: data/evaluation/eval_report.json -- "
        "the ONE stable filename this script ever writes; contrast with "
        "scripts/run_safety_benchmark.py's timestamped reports).",
    )
    parser.add_argument(
        "--safety-runs",
        type=int,
        default=1,
        help="k for the safety benchmark sub-run. Defaults to 1, not the official "
        "k=3, because the mock provider is deterministic -- see this script's module "
        "docstring for why. Pass --safety-runs 3 to reproduce the official methodology.",
    )
    parser.add_argument(
        "--safety-limit",
        type=int,
        default=None,
        help="Debug/dev only: run just the first N safety-benchmark cases. Never use "
        "for a report anyone will read.",
    )
    parser.add_argument(
        "--safety-cases-dir",
        default=None,
        help="Override the safety benchmark cases directory (default: the frozen set "
        "in app/evaluation/benchmark/cases/).",
    )
    parser.add_argument(
        "--skip-retrieval",
        action="store_true",
        help="Skip the retrieval suite even if a Chroma collection is present "
        "(it is auto-skipped anyway when the collection is empty).",
    )
    parser.add_argument(
        "--skip-constraints",
        action="store_true",
        help="Skip the constraint smoke suite.",
    )
    return parser


def _default_report_path() -> Path:
    return ROOT / "data" / "evaluation" / "eval_report.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    report_path = Path(args.report_path) if args.report_path else _default_report_path()

    print(f"Running safety benchmark suite (mock provider, runs={args.safety_runs})...")
    safety_suite = run_safety_suite(
        runs=args.safety_runs, limit=args.safety_limit, cases_dir=args.safety_cases_dir
    )
    print(
        f"  inherent: raw judge-flagged {safety_suite.inherent.raw_judge_flagged_count}/"
        f"{safety_suite.inherent.total_cases}, adjudicated-true "
        f"{safety_suite.inherent.adjudicated_true_count}/{safety_suite.inherent.total_cases} "
        f"-- release_gate_pass={safety_suite.release_gate_pass}"
    )

    notes: list[str] = []
    if args.skip_retrieval:
        retrieval_suite = RetrievalSuite(skipped=True, skip_reason="--skip-retrieval passed")
    else:
        print("Running retrieval suite...")
        retrieval_suite = run_retrieval_suite()
        if retrieval_suite.skipped:
            print(f"  skipped: {retrieval_suite.skip_reason}")
            notes.append("retrieval suite skipped: " + (retrieval_suite.skip_reason or ""))
        else:
            print(f"  {retrieval_suite.query_count} queries, gate_pass={retrieval_suite.gate_pass}")

    if args.skip_constraints:
        constraint_suite = ConstraintSuite(total_recipes=0, profiles=[], sane=True)
        notes.append("constraint suite skipped: --skip-constraints passed")
    else:
        print("Running constraint smoke suite...")
        constraint_suite = run_constraint_suite()
        print(
            f"  {len(constraint_suite.profiles)} profiles over "
            f"{constraint_suite.total_recipes} recipes, sane={constraint_suite.sane}"
        )

    report = EvalReport(
        generated_at_utc=datetime.now(UTC).isoformat(),
        git_commit=safety_mod._git_commit_hash(),
        safety_benchmark=safety_suite,
        retrieval=retrieval_suite,
        constraints=constraint_suite,
        notes=notes,
    )
    report.deltas_vs_previous = _compute_deltas(report_path, report)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nWrote {report_path}")

    return 0 if safety_suite.release_gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
