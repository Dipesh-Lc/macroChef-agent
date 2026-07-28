import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { getLatestEvalReport } from "../api/endpoints";
import type {
  ConstraintProfileResult,
  ConstraintSuite,
  EvalReport,
  RetrievalCategoryResult,
  RetrievalSuite,
  SafetyBenchmarkBucket,
  SafetyBenchmarkSuite,
} from "../api/types";
import { formatPercent } from "../lib/format";

/**
 * ROADMAP 4.6: public, unauthenticated eval & methodology page. Fetches
 * `GET /evals/latest` (`app.api.routes_evals`) and renders whatever it
 * returns -- this page computes and enforces NOTHING itself (no safety
 * decision, no nutrition math, no re-scoring): every number here is read
 * straight off the committed report `scripts/run_all_evals.py` wrote.
 *
 * Matches `LandingPage.tsx`'s GitHub URL constant -- kept as a separate
 * literal (not imported) because these two pages have no other shared
 * module and a tiny constant duplicated twice is simpler than introducing
 * one for a single string.
 */
const GITHUB_REPO_URL = "https://github.com/Dipesh-Lc/macroChef-agent";
const SAFETY_CASES_URL = `${GITHUB_REPO_URL}/tree/main/app/evaluation/benchmark/cases`;
const RETRIEVAL_QUERIES_URL = `${GITHUB_REPO_URL}/blob/main/app/evaluation/data/retrieval_eval_queries.jsonl`;
const CONSTRAINT_SUITE_SOURCE_URL = `${GITHUB_REPO_URL}/blob/main/app/evaluation/eval_constraints.py`;
const RUN_ALL_EVALS_SOURCE_URL = `${GITHUB_REPO_URL}/blob/main/scripts/run_all_evals.py`;

type LoadState =
  | { status: "loading" }
  | { status: "not_generated"; message: string }
  | { status: "error"; message: string }
  | { status: "ready"; report: EvalReport };

function GateBadge({ pass, label }: { pass: boolean | null; label: string }) {
  if (pass === null) {
    return (
      <span className="rounded-full border border-dashed border-sage-line px-2.5 py-1 text-xs font-medium uppercase tracking-wide text-cast-iron/50">
        {label}: n/a
      </span>
    );
  }
  const className = pass
    ? "rounded-full bg-basil/15 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-basil-dark"
    : "rounded-full bg-chili/15 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-chili-dark";
  return <span className={className}>{label}: {pass ? "pass" : "fail"}</span>;
}

function SuiteCard({
  title,
  description,
  sourceHref,
  sourceLabel,
  badge,
  children,
}: {
  title: string;
  description: string;
  sourceHref: string;
  sourceLabel: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-display text-lg font-semibold text-cast-iron">{title}</h2>
          <p className="max-w-2xl text-sm text-cast-iron/70">{description}</p>
        </div>
        {badge}
      </div>
      {children}
      <a
        href={sourceHref}
        target="_blank"
        rel="noreferrer"
        className="self-start text-xs font-medium text-cast-iron/60 underline underline-offset-2 hover:text-basil"
      >
        {sourceLabel}
      </a>
    </section>
  );
}

const BUCKET_LABEL: Record<string, string> = {
  inherent: "Inherent (release-blocking)",
  precautionary: "Precautionary",
  safe_control_over_block: "Safe control (over-block check)",
};

function SafetyBucketRow({ bucketKey, bucket }: { bucketKey: string; bucket: SafetyBenchmarkBucket }) {
  return (
    <tr className="border-t border-sage-line align-top">
      <td className="px-2 py-1.5">{BUCKET_LABEL[bucketKey] ?? bucketKey}</td>
      <td className="px-2 py-1.5 font-mono">{bucket.total_cases}</td>
      <td className="px-2 py-1.5 font-mono">
        {bucket.raw_judge_flagged_count} ({formatPercent(bucket.raw_judge_flagged_rate, 1)})
      </td>
      <td className="px-2 py-1.5 font-mono text-cast-iron/70">
        {formatPercent(bucket.wilson_lower, 1)}–{formatPercent(bucket.wilson_upper, 1)}
      </td>
      <td className="px-2 py-1.5 font-mono">
        {bucket.adjudicated_true_count === null || bucket.adjudicated_true_count === undefined
          ? "n/a — not release-blocking"
          : bucket.adjudicated_true_count}
      </td>
    </tr>
  );
}

function SafetySuiteSection({ safety }: { safety: SafetyBenchmarkSuite }) {
  const buckets: [string, SafetyBenchmarkBucket][] = [
    ["inherent", safety.inherent],
    ["precautionary", safety.precautionary],
    ["safe_control_over_block", safety.safe_control_over_block],
  ];
  const categoryBreakdown = safety.category_breakdown ?? [];

  return (
    <SuiteCard
      title="Adversarial safety benchmark"
      description="Scores the deterministic allergy/diet safety layer against hand-authored adversarial cases (hidden allergens, prompt injection, morphology confusions, diet traps). The raw judge-flagged count and the adjudicated-true count are always published together — the judge is a deliberately paranoid substring matcher, and the adjudicated number is an exhaustive re-check against the real production constraint-engine code, never a sample."
      sourceHref={SAFETY_CASES_URL}
      sourceLabel="View the case files on GitHub"
      badge={<GateBadge pass={safety.release_gate_pass} label="Release gate" />}
    >
      <div className="text-xs text-cast-iron/60">
        Provider: <span className="font-mono">{safety.provider}</span> · Runs per case set:{" "}
        <span className="font-mono">{safety.runs}</span> · Total cases:{" "}
        <span className="font-mono">{safety.total_cases}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
            <tr>
              <th className="px-2 py-1.5 font-medium">Bucket</th>
              <th className="px-2 py-1.5 font-medium">Cases</th>
              <th className="px-2 py-1.5 font-medium">Raw judge-flagged</th>
              <th className="px-2 py-1.5 font-medium">Wilson 95% CI</th>
              <th className="px-2 py-1.5 font-medium">Adjudicated-true</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map(([key, bucket]) => (
              <SafetyBucketRow key={key} bucketKey={key} bucket={bucket} />
            ))}
          </tbody>
        </table>
      </div>

      {categoryBreakdown.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-cast-iron/50">
            Category breakdown (worst run, inherent bucket scoring)
          </h3>
          <div className="mt-1 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
                <tr>
                  <th className="px-2 py-1.5 font-medium">Category</th>
                  <th className="px-2 py-1.5 font-medium">Cases</th>
                  <th className="px-2 py-1.5 font-medium">Raw judge-flagged</th>
                </tr>
              </thead>
              <tbody>
                {categoryBreakdown.map((row) => (
                  <tr key={row.category} className="border-t border-sage-line">
                    <td className="px-2 py-1.5 font-mono">{row.category}</td>
                    <td className="px-2 py-1.5 font-mono">{row.total_cases}</td>
                    <td className="px-2 py-1.5 font-mono">{row.raw_judge_flagged_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SuiteCard>
  );
}

function RetrievalCategoryRow({ row }: { row: RetrievalCategoryResult }) {
  return (
    <tr className="border-t border-sage-line">
      <td className="px-2 py-1.5">
        {row.category}
        {row.gated && (
          <span className="ml-1.5 rounded-full border border-sage-line px-1.5 py-0.5 text-[0.65rem] uppercase text-cast-iron/50">
            gated
          </span>
        )}
      </td>
      <td className="px-2 py-1.5 font-mono">{row.semantic_mrr.toFixed(3)}</td>
      <td className="px-2 py-1.5 font-mono">{row.keyword_mrr.toFixed(3)}</td>
      <td className="px-2 py-1.5 font-mono">{row.hybrid_mrr.toFixed(3)}</td>
      <td className="px-2 py-1.5 font-mono">{formatPercent(row.semantic_recall_at_10)}</td>
      <td className="px-2 py-1.5 font-mono">{formatPercent(row.keyword_recall_at_10)}</td>
      <td className="px-2 py-1.5 font-mono">{formatPercent(row.hybrid_recall_at_10)}</td>
      <td className="px-2 py-1.5 font-mono">
        {row.win === null || row.win === undefined ? "—" : row.win ? "win" : "no"}
      </td>
    </tr>
  );
}

function RetrievalSuiteSection({ retrieval }: { retrieval: RetrievalSuite }) {
  return (
    <SuiteCard
      title="Retrieval quality"
      description="Compares semantic, keyword, and hybrid recipe search on a hand-labeled query set. Gated categories must show semantic strictly beating keyword search on both MRR and Recall@10, with hybrid never regressing past a small tolerance — this is the gate scripts/evaluate_retrieval.py enforces before a corpus/embedding change ships."
      sourceHref={RETRIEVAL_QUERIES_URL}
      sourceLabel="View the eval queries on GitHub"
      badge={<GateBadge pass={retrieval.gate_pass ?? null} label="Retrieval gate" />}
    >
      {retrieval.skipped ? (
        <p className="rounded-md border border-dashed border-sage-line bg-porcelain px-3 py-2 text-sm text-cast-iron/70">
          Skipped: {retrieval.skip_reason ?? "no reason recorded"}
        </p>
      ) : (
        <>
          <div className="text-xs text-cast-iron/60">
            Queries scored: <span className="font-mono">{retrieval.query_count}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
                <tr>
                  <th className="px-2 py-1.5 font-medium">Category</th>
                  <th className="px-2 py-1.5 font-medium">Semantic MRR</th>
                  <th className="px-2 py-1.5 font-medium">Keyword MRR</th>
                  <th className="px-2 py-1.5 font-medium">Hybrid MRR</th>
                  <th className="px-2 py-1.5 font-medium">Semantic Recall@10</th>
                  <th className="px-2 py-1.5 font-medium">Keyword Recall@10</th>
                  <th className="px-2 py-1.5 font-medium">Hybrid Recall@10</th>
                  <th className="px-2 py-1.5 font-medium">Result</th>
                </tr>
              </thead>
              <tbody>
                {(retrieval.categories ?? []).map((row) => (
                  <RetrievalCategoryRow key={row.category} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </SuiteCard>
  );
}

function ConstraintProfileRow({ profile }: { profile: ConstraintProfileResult }) {
  const constraintLabel =
    profile.allergies.length === 0 && !profile.diet_type
      ? "none (baseline)"
      : [profile.allergies.join(", "), profile.diet_type].filter(Boolean).join(" · ");
  return (
    <tr className="border-t border-sage-line">
      <td className="px-2 py-1.5">{profile.label}</td>
      <td className="px-2 py-1.5 text-cast-iron/70">{constraintLabel}</td>
      <td className="px-2 py-1.5 font-mono">{profile.total_recipes}</td>
      <td className="px-2 py-1.5 font-mono">{profile.valid}</td>
      <td className="px-2 py-1.5 font-mono">{profile.rejected}</td>
    </tr>
  );
}

function ConstraintSuiteSection({ constraints }: { constraints: ConstraintSuite }) {
  return (
    <SuiteCard
      title="Constraint smoke suite"
      description="Runs a representative spread of allergy/diet profiles over the full recipe corpus through the real constraint_engine.validate_recipe. This is a coverage/sanity check, not a graded-correctness metric — there's no external ground truth for how many recipes a given profile 'should' reject, so it watches for the two shapes that indicate a real bug: the unrestricted baseline rejecting anything, or a restrictive profile rejecting nothing."
      sourceHref={CONSTRAINT_SUITE_SOURCE_URL}
      sourceLabel="View eval_constraints.py on GitHub"
      badge={<GateBadge pass={constraints.sane} label="Sanity check" />}
    >
      <div className="text-xs text-cast-iron/60">
        Corpus size: <span className="font-mono">{constraints.total_recipes}</span> recipes
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
            <tr>
              <th className="px-2 py-1.5 font-medium">Profile</th>
              <th className="px-2 py-1.5 font-medium">Constraints</th>
              <th className="px-2 py-1.5 font-medium">Corpus</th>
              <th className="px-2 py-1.5 font-medium">Valid</th>
              <th className="px-2 py-1.5 font-medium">Rejected</th>
            </tr>
          </thead>
          <tbody>
            {constraints.profiles.map((profile) => (
              <ConstraintProfileRow key={profile.label} profile={profile} />
            ))}
          </tbody>
        </table>
      </div>
    </SuiteCard>
  );
}

function DeltasSection({ report }: { report: EvalReport }) {
  const deltas = report.deltas_vs_previous ?? {};
  const entries = Object.entries(deltas);
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="rounded-lg border border-dashed border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Since the previous run</h2>
      <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-2 border-b border-sage-line/60 py-1">
            <dt className="text-cast-iron/60">{key.replace(/_/g, " ")}</dt>
            <dd className="font-mono text-cast-iron">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function NotGeneratedState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-sage-line bg-white px-6 py-16 text-center">
      <h1 className="font-display text-xl font-semibold text-cast-iron">No eval report yet</h1>
      <p className="max-w-lg text-sm text-cast-iron/70">{message}</p>
      <p className="max-w-lg text-xs text-cast-iron/50">
        This is an ordinary state, not an error: the report is a deliberate, out-of-band artifact
        written by a script run, never generated as a side effect of visiting this page. See{" "}
        <a
          href={RUN_ALL_EVALS_SOURCE_URL}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-basil"
        >
          scripts/run_all_evals.py
        </a>{" "}
        for what it runs and why.
      </p>
      <Link
        to="/"
        className="mt-2 rounded-md border border-sage-line px-4 py-2 text-sm font-semibold text-cast-iron transition-colors hover:bg-sage-line/40"
      >
        Back to MacroChef
      </Link>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-chili bg-chili/5 px-6 py-16 text-center">
      <h1 className="font-display text-xl font-semibold text-cast-iron">Could not load the eval report</h1>
      <p className="max-w-md text-sm text-cast-iron/70">{message}</p>
    </div>
  );
}

export default function EvalsPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getLatestEvalReport()
      .then((result) => {
        if (cancelled) {
          return;
        }
        if ("status" in result && result.status === "not_generated") {
          setState({ status: "not_generated", message: result.message });
        } else {
          setState({ status: "ready", report: result as EvalReport });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof ApiError
            ? error.message
            : "Could not load the eval report. Please try again.";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-8 py-6">
      <header className="flex flex-col gap-2">
        <span className="font-mono text-xs font-semibold uppercase tracking-widest text-basil">
          Eval report
        </span>
        <h1 className="font-display text-3xl font-semibold text-cast-iron sm:text-4xl">
          What we actually measure, and how
        </h1>
        <p className="max-w-2xl text-sm text-cast-iron/70 sm:text-base">
          Every number on this page is read directly from a committed report file — never
          recomputed by this page, never phrased by an LLM. Safety numbers always show the raw
          judge-flagged count alongside the adjudicated-true count, per this project's
          release-gate policy: the judge is never modified to close the gap.
        </p>
      </header>

      {state.status === "loading" && (
        <div className="h-40 animate-pulse rounded-lg border border-dashed border-sage-line bg-white" />
      )}

      {state.status === "not_generated" && <NotGeneratedState message={state.message} />}

      {state.status === "error" && <ErrorState message={state.message} />}

      {state.status === "ready" && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-3 text-xs text-cast-iron/60">
            <span>
              Run date:{" "}
              <span className="font-mono text-cast-iron">
                {new Date(state.report.generated_at_utc).toLocaleString()}
              </span>
            </span>
            <span>
              Commit: <span className="font-mono text-cast-iron">{state.report.git_commit}</span>
            </span>
          </div>

          {(state.report.notes ?? []).length > 0 && (
            <ul className="flex flex-col gap-1 text-xs text-cast-iron/60">
              {(state.report.notes ?? []).map((note, index) => (
                <li key={index}>Note: {note}</li>
              ))}
            </ul>
          )}

          <SafetySuiteSection safety={state.report.safety_benchmark} />
          <RetrievalSuiteSection retrieval={state.report.retrieval} />
          <ConstraintSuiteSection constraints={state.report.constraints} />
          <DeltasSection report={state.report} />
        </div>
      )}
    </div>
  );
}
