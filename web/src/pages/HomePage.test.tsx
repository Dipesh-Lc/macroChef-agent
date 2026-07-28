import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MealRecommendation, Recipe, RecipeScore, RecommendationResponse } from "../api/types";
import type { NodeRunEvent, RecommendStreamEvent } from "../lib/sse";
import HomePage from "./HomePage";

// "See more" pagination on the Find-recipes results: with a longer
// recommendations list (a backend change elsewhere raises the return count
// from 3 to ~20), only `visibleCount` (default 5) render initially, and
// clicking "See more" reveals 5 more at a time until the whole list is
// visible and the button disappears.

vi.mock("../api/endpoints", () => ({
  recommendRecipes: vi.fn(),
  extractInventory: vi.fn(),
  postFeedback: vi.fn(),
}));

// `streamRecommend` (ROADMAP Step 4.2) is the primary path HomePage now
// drives via `useRecommendStream` -- mocked here (rather than faking a raw
// `Response`/`ReadableStream`) so each streaming test can script exactly
// which typed events arrive and when, using the "controlled generator"
// helper below. `recommendRecipes` (mocked above) stays wired in as
// HomePage's zero-events sync fallback -- see its own test group.
vi.mock("../lib/sse", () => ({
  streamRecommend: vi.fn(),
}));

import { recommendRecipes } from "../api/endpoints";
import { streamRecommend } from "../lib/sse";

/**
 * An async generator whose `push`/`fail`/`finish` are driven from OUTSIDE
 * the generator body -- lets a test yield one `RecommendStreamEvent` at a
 * time and `await waitFor(...)` the resulting UI update before pushing the
 * next one, the same way a real SSE stream delivers events over time
 * instead of all at once.
 */
function controlledStream() {
  const queue: RecommendStreamEvent[] = [];
  let wake: (() => void) | null = null;
  let finished = false;
  let failure: unknown = null;

  async function* generator(): AsyncGenerator<RecommendStreamEvent> {
    while (true) {
      if (queue.length > 0) {
        yield queue.shift() as RecommendStreamEvent;
        continue;
      }
      if (failure) {
        throw failure;
      }
      if (finished) {
        return;
      }
      await new Promise<void>((resolve) => {
        wake = resolve;
      });
    }
  }

  return {
    generator,
    push(event: RecommendStreamEvent) {
      queue.push(event);
      wake?.();
      wake = null;
    },
    finish() {
      finished = true;
      wake?.();
      wake = null;
    },
    fail(error: unknown) {
      failure = error;
      wake?.();
      wake = null;
    },
  };
}

function buildNodeEvent(overrides: Partial<NodeRunEvent>): NodeRunEvent {
  return {
    run_id: "r1",
    node: "intake_node",
    status: "finished",
    elapsed_ms: 10,
    summary: "intake_node: parsed ingredients.",
    payload: {},
    ts: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function buildRecipe(index: number): Recipe {
  return {
    recipe_id: `recipe_${index}`,
    title: `Recipe ${index}`,
    ingredients: [],
    instructions: ["Cook."],
    nutrition: null,
    servings: 1,
    source_type: "imported",
    is_user_saved: false,
    is_active: true,
    restored_from_quarantine: false,
    derived_allergens: [],
  };
}

function buildScore(index: number): RecipeScore {
  return {
    recipe_id: `recipe_${index}`,
    pantry_match_score: 0.5,
    pantry_mass_coverage: 0.5,
    macro_fit_score: 0.5,
    time_score: 0.5,
    preference_score: 0.5,
    final_score: 0.5,
    missing_ingredients: [],
    used_ingredients: [],
  };
}

function buildRecommendations(count: number): MealRecommendation[] {
  return Array.from({ length: count }, (_, index) => ({
    recipe: buildRecipe(index),
    score: buildScore(index),
    explanation: `Explanation ${index}`,
  }));
}

function buildResponse(count: number): RecommendationResponse {
  return {
    recommendations: buildRecommendations(count),
    rejected_recipes: [],
    shopping_list: [],
    errors: [],
  };
}

function renderHomePage() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <HomePage />
    </QueryClientProvider>,
  );
}

// Every test in the existing "See more" pagination suite below predates
// streaming and asserts on the plain sync-endpoint flow -- rather than
// rewrite them, this default `streamRecommend` mock always fails before
// yielding a single event, which is exactly the condition
// `useRecommendStream` (HomePage.tsx) falls back to `recommendRecipes` for
// (see that hook's docstring). Individual streaming tests below override
// this per-test with `controlledStream()` instead.
//
// Implemented as a manual `AsyncGenerator` object rather than an
// `async function*` body -- a generator function whose body never reaches a
// `yield` trips ESLint's `require-yield`, and there's nothing to yield here:
// this generator's only job is to reject its very first `next()` call.
function immediateTransportFailure(): AsyncGenerator<RecommendStreamEvent> {
  const error = new Error("stream transport unavailable in this test");
  const generator: AsyncGenerator<RecommendStreamEvent> = {
    [Symbol.asyncIterator]() {
      return generator;
    },
    next() {
      return Promise.reject(error);
    },
    return(value) {
      return Promise.resolve({ done: true, value } as IteratorResult<RecommendStreamEvent>);
    },
    throw(thrown) {
      return Promise.reject(thrown);
    },
  };
  return generator;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(recommendRecipes).mockReset();
  vi.mocked(streamRecommend).mockReset();
  vi.mocked(streamRecommend).mockImplementation(() => immediateTransportFailure());
});

describe("HomePage See more pagination (sync fallback path)", () => {
  it("renders only 5 recipes initially, then reveals 5 more per click, then all, hiding the button", async () => {
    vi.mocked(recommendRecipes).mockResolvedValue(buildResponse(12));
    renderHomePage();

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));

    await waitFor(() => expect(screen.getByText("Recipe 0")).toBeInTheDocument());
    for (let i = 0; i < 5; i++) {
      expect(screen.getByText(`Recipe ${i}`)).toBeInTheDocument();
    }
    for (let i = 5; i < 12; i++) {
      expect(screen.queryByText(`Recipe ${i}`)).not.toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: /see more/i }));
    await waitFor(() => expect(screen.getByText("Recipe 9")).toBeInTheDocument());
    for (let i = 0; i < 10; i++) {
      expect(screen.getByText(`Recipe ${i}`)).toBeInTheDocument();
    }
    for (let i = 10; i < 12; i++) {
      expect(screen.queryByText(`Recipe ${i}`)).not.toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: /see more/i }));
    await waitFor(() => expect(screen.getByText("Recipe 11")).toBeInTheDocument());
    for (let i = 0; i < 12; i++) {
      expect(screen.getByText(`Recipe ${i}`)).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /see more/i })).not.toBeInTheDocument();
  });

  it("resets visibleCount back to 5 when a new search is run", async () => {
    vi.mocked(recommendRecipes).mockResolvedValue(buildResponse(12));
    renderHomePage();

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));
    await waitFor(() => expect(screen.getByText("Recipe 0")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /see more/i }));
    await waitFor(() => expect(screen.getByText("Recipe 9")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));
    await waitFor(() => expect(vi.mocked(recommendRecipes).mock.calls.length).toBe(2));

    for (let i = 0; i < 5; i++) {
      expect(screen.getByText(`Recipe ${i}`)).toBeInTheDocument();
    }
    for (let i = 5; i < 12; i++) {
      expect(screen.queryByText(`Recipe ${i}`)).not.toBeInTheDocument();
    }
  });
});

describe("HomePage live streaming progress (ROADMAP 4.2)", () => {
  it("renders node events in arrival order, then swaps in real results on the terminal `result` event", async () => {
    const stream = controlledStream();
    vi.mocked(streamRecommend).mockImplementation(() => stream.generator());
    renderHomePage();

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));

    act(() =>
      stream.push({
        type: "node",
        data: buildNodeEvent({ node: "intake_node", status: "started", elapsed_ms: null }),
      }),
    );
    await waitFor(() => expect(screen.getByText("Intake")).toBeInTheDocument());
    // Nothing else has arrived yet.
    expect(screen.queryByText("Constraint Builder")).not.toBeInTheDocument();

    act(() =>
      stream.push({
        type: "node",
        data: buildNodeEvent({ node: "intake_node", status: "finished", elapsed_ms: 5 }),
      }),
    );
    act(() =>
      stream.push({
        type: "node",
        data: buildNodeEvent({ node: "constraint_builder_node", status: "finished", elapsed_ms: 9 }),
      }),
    );
    await waitFor(() => expect(screen.getByText("Constraint Builder")).toBeInTheDocument());

    // Both rows are still visible and in order -- "filled in", not replaced.
    const rows = screen.getAllByText(/^(Intake|Constraint Builder)$/);
    expect(rows.map((row) => row.textContent)).toEqual(["Intake", "Constraint Builder"]);

    act(() => {
      stream.push({ type: "result", data: buildResponse(2) });
      stream.finish();
    });

    await waitFor(() => expect(screen.getByText("Recipe 0")).toBeInTheDocument());
    // The timeline is gone once real results have swapped in.
    expect(screen.queryByText("Intake")).not.toBeInTheDocument();
  });

  it("renders a safety_filter_node rejection event's summary in chili while streaming", async () => {
    const stream = controlledStream();
    vi.mocked(streamRecommend).mockImplementation(() => stream.generator());
    renderHomePage();

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));

    act(() =>
      stream.push({
        type: "node",
        data: buildNodeEvent({
          node: "safety_filter_node",
          status: "finished",
          elapsed_ms: 4,
          summary: "safety_filter_node: 3 valid, 1 total rejected.",
        }),
      }),
    );

    await waitFor(() =>
      expect(screen.getByText("safety_filter_node: 3 valid, 1 total rejected.")).toBeInTheDocument(),
    );
    const summary = screen.getByText("safety_filter_node: 3 valid, 1 total rejected.");
    expect(summary.className).toContain("text-chili");
  });

  it("on an `error` event, shows the partial trace plus a retry affordance that re-runs the stream", async () => {
    const firstStream = controlledStream();
    const secondStream = controlledStream();
    vi.mocked(streamRecommend)
      .mockImplementationOnce(() => firstStream.generator())
      .mockImplementationOnce(() => secondStream.generator());
    renderHomePage();

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));

    act(() =>
      firstStream.push({
        type: "node",
        data: buildNodeEvent({ node: "intake_node", status: "finished" }),
      }),
    );
    await waitFor(() => expect(screen.getByText("Intake")).toBeInTheDocument());

    act(() => {
      firstStream.push({ type: "error", data: { detail: "Internal Server Error", error_type: "RuntimeError" } });
      firstStream.finish();
    });

    await waitFor(() => expect(screen.getByText("Internal Server Error")).toBeInTheDocument());
    // The partial trace collected before the failure is still visible.
    expect(screen.getByText("Intake")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    act(() => {
      secondStream.push({ type: "result", data: buildResponse(1) });
      secondStream.finish();
    });

    await waitFor(() => expect(screen.getByText("Recipe 0")).toBeInTheDocument());
    expect(vi.mocked(streamRecommend)).toHaveBeenCalledTimes(2);
  });

  it("falls back to the synchronous endpoint when the stream fails before any event arrives", async () => {
    vi.mocked(streamRecommend).mockImplementation(() => immediateTransportFailure());
    vi.mocked(recommendRecipes).mockResolvedValue(buildResponse(1));
    renderHomePage();

    fireEvent.click(screen.getByRole("button", { name: /find recipes/i }));

    await waitFor(() => expect(screen.getByText("Recipe 0")).toBeInTheDocument());
    expect(vi.mocked(recommendRecipes)).toHaveBeenCalledTimes(1);
    // No lingering error panel -- the fallback succeeded transparently.
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
