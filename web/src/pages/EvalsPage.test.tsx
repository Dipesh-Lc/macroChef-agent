import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EvalReport } from "../api/types";
import EvalsPage from "./EvalsPage";

// ROADMAP 4.6: EvalsPage consumes `GET /evals/latest` via the
// `getLatestEvalReport` wrapper (api/endpoints.ts) -- mocked here the same
// way SharedPlanPage.test.tsx mocks `getSharedPlan`, per this repo's no-msw
// convention.
vi.mock("../api/endpoints", () => ({
  getLatestEvalReport: vi.fn(),
}));

import { getLatestEvalReport } from "../api/endpoints";

function renderEvalsPage() {
  return render(
    <MemoryRouter initialEntries={["/evals"]}>
      <Routes>
        <Route path="/evals" element={<EvalsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// A realistic fixture matching the actual `EvalReport` Pydantic schema
// (`app.schemas.evals.EvalReport`) -- every field present on the real
// model, not a hand-picked subset.
const REALISTIC_REPORT: EvalReport = {
  generated_at_utc: "2026-07-28T18:30:00+00:00",
  git_commit: "06372b1",
  safety_benchmark: {
    provider: "mock",
    runs: 1,
    total_cases: 371,
    inherent: {
      label: "inherent",
      total_cases: 269,
      raw_judge_flagged_count: 73,
      raw_judge_flagged_rate: 0.2714,
      wilson_lower: 0.2216,
      wilson_upper: 0.327,
      raw_judge_flagged_case_ids: ["case-001", "case-002"],
      adjudicated_true_count: 0,
      adjudicated_true_case_ids: [],
    },
    precautionary: {
      label: "precautionary",
      total_cases: 42,
      raw_judge_flagged_count: 5,
      raw_judge_flagged_rate: 0.119,
      wilson_lower: 0.05,
      wilson_upper: 0.25,
      raw_judge_flagged_case_ids: [],
      adjudicated_true_count: null,
      adjudicated_true_case_ids: null,
    },
    safe_control_over_block: {
      label: "safe_control_over_block",
      total_cases: 60,
      raw_judge_flagged_count: 0,
      raw_judge_flagged_rate: 0,
      wilson_lower: 0,
      wilson_upper: 0.06,
      raw_judge_flagged_case_ids: [],
      adjudicated_true_count: null,
      adjudicated_true_case_ids: null,
    },
    category_breakdown: [
      { category: "hidden_allergen", total_cases: 40, raw_judge_flagged_count: 12 },
      { category: "prompt_injection", total_cases: 35, raw_judge_flagged_count: 8 },
    ],
    release_gate_pass: true,
  },
  retrieval: {
    skipped: false,
    skip_reason: null,
    query_count: 120,
    gate_pass: true,
    categories: [
      {
        category: "allergen_synonym",
        gated: true,
        semantic_mrr: 0.812,
        keyword_mrr: 0.65,
        hybrid_mrr: 0.8,
        semantic_recall_at_10: 0.91,
        keyword_recall_at_10: 0.7,
        hybrid_recall_at_10: 0.89,
        win: true,
      },
    ],
  },
  constraints: {
    total_recipes: 4238,
    profiles: [
      {
        label: "no_restrictions",
        allergies: [],
        diet_type: null,
        total_recipes: 4238,
        valid: 4238,
        rejected: 0,
      },
      {
        label: "peanut_allergy",
        allergies: ["peanut"],
        diet_type: null,
        total_recipes: 4238,
        valid: 4100,
        rejected: 138,
      },
    ],
    sane: true,
  },
  deltas_vs_previous: {
    previous_generated_at_utc: "2026-07-27T18:30:00+00:00",
    inherent_raw_judge_flagged_count_delta: 0,
  },
  notes: [],
};

beforeEach(() => {
  vi.mocked(getLatestEvalReport).mockReset();
});

describe("EvalsPage", () => {
  it("renders suite cards from a realistic EvalReport fixture", async () => {
    vi.mocked(getLatestEvalReport).mockResolvedValue(REALISTIC_REPORT);

    renderEvalsPage();

    await waitFor(() =>
      expect(screen.getByText(/adversarial safety benchmark/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/retrieval quality/i)).toBeInTheDocument();
    expect(screen.getByText(/constraint smoke suite/i)).toBeInTheDocument();

    // Category breakdown table renders real category names.
    expect(screen.getByText("hidden_allergen")).toBeInTheDocument();
    expect(screen.getByText("prompt_injection")).toBeInTheDocument();

    // Retrieval and constraint numbers render.
    expect(screen.getByText("0.812")).toBeInTheDocument();
    expect(screen.getByText("peanut_allergy")).toBeInTheDocument();

    // Run date + commit are shown.
    expect(screen.getByText("06372b1")).toBeInTheDocument();
  });

  it("always shows both the raw judge-flagged count and the adjudicated-true count for the inherent bucket, never collapsed to one number", async () => {
    vi.mocked(getLatestEvalReport).mockResolvedValue(REALISTIC_REPORT);

    renderEvalsPage();

    await waitFor(() =>
      expect(screen.getByText(/adversarial safety benchmark/i)).toBeInTheDocument(),
    );

    // Raw judge-flagged count (73) and its rate.
    expect(screen.getByText(/73 \(27\.1%\)/)).toBeInTheDocument();
    // Adjudicated-true count (0) for the inherent bucket -- rendered as its
    // own table cell, distinct from the raw count above.
    const inherentRow = screen.getByText("Inherent (release-blocking)").closest("tr");
    expect(inherentRow).not.toBeNull();
    expect(inherentRow).toHaveTextContent("0");
    // Non-blocking buckets explicitly show "n/a", never a fabricated number.
    expect(screen.getAllByText(/n\/a — not release-blocking/i).length).toBe(2);
  });

  it("renders a polished 'not yet generated' empty state when the endpoint returns EvalReportNotAvailable", async () => {
    vi.mocked(getLatestEvalReport).mockResolvedValue({
      status: "not_generated",
      message:
        "No eval report has been generated yet. Run `python scripts/run_all_evals.py` to produce data/evaluation/eval_report.json.",
    });

    renderEvalsPage();

    await waitFor(() => expect(screen.getByText(/no eval report yet/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /scripts\/run_all_evals\.py/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to macrochef/i })).toHaveAttribute("href", "/");
    // Never renders suite cards in this state.
    expect(screen.queryByText(/adversarial safety benchmark/i)).not.toBeInTheDocument();
  });

  it("renders an error state on a request failure, distinct from the not-generated state", async () => {
    const { ApiError } = await import("../api/client");
    vi.mocked(getLatestEvalReport).mockRejectedValue(new ApiError(502, "corrupt report"));

    renderEvalsPage();

    await waitFor(() =>
      expect(screen.getByText(/could not load the eval report/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/no eval report yet/i)).not.toBeInTheDocument();
  });
});
