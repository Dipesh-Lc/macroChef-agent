import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunProgressTimeline } from "./RunProgressTimeline";
import type { NodeRunEvent } from "../lib/sse";

function nodeEvent(overrides: Partial<NodeRunEvent>): NodeRunEvent {
  return {
    run_id: "r1",
    node: "intake_node",
    status: "finished",
    elapsed_ms: 12.3,
    summary: "intake_node: parsed 3 ingredients.",
    payload: {},
    ts: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("RunProgressTimeline", () => {
  it("renders one row per node, in the order each node first appeared", () => {
    const events: NodeRunEvent[] = [
      nodeEvent({ node: "intake_node", status: "started", elapsed_ms: null }),
      nodeEvent({ node: "intake_node", status: "finished", elapsed_ms: 10 }),
      nodeEvent({ node: "constraint_builder_node", status: "started", elapsed_ms: null }),
      nodeEvent({ node: "constraint_builder_node", status: "finished", elapsed_ms: 20 }),
    ];

    render(<RunProgressTimeline events={events} phase="streaming" />);

    const rows = screen.getAllByText(/Intake|Constraint Builder/);
    expect(rows.map((row) => row.textContent)).toEqual(["Intake", "Constraint Builder"]);
    // The row shows the LATEST event for that node (finished, with its
    // elapsed time), not a duplicate row for the earlier "started" event.
    expect(screen.getByText("10ms")).toBeInTheDocument();
    expect(screen.getByText("20ms")).toBeInTheDocument();
  });

  it("renders a safety_filter_node rejection summary in the chili color class", () => {
    const events: NodeRunEvent[] = [
      nodeEvent({
        node: "safety_filter_node",
        status: "finished",
        elapsed_ms: 5,
        summary: "safety_filter_node: 3 valid, 2 total rejected.",
      }),
    ];

    render(<RunProgressTimeline events={events} phase="streaming" />);

    const summary = screen.getByText("safety_filter_node: 3 valid, 2 total rejected.");
    expect(summary.className).toContain("text-chili");
  });

  it("does not chili-color a safety_filter_node summary with zero rejections", () => {
    const events: NodeRunEvent[] = [
      nodeEvent({
        node: "safety_filter_node",
        status: "finished",
        elapsed_ms: 5,
        summary: "safety_filter_node: 5 valid, 0 total rejected.",
      }),
    ];

    render(<RunProgressTimeline events={events} phase="streaming" />);

    const summary = screen.getByText("safety_filter_node: 5 valid, 0 total rejected.");
    expect(summary.className).not.toContain("text-chili");
  });

  it("chili-colors any failed node's summary regardless of node name", () => {
    const events: NodeRunEvent[] = [
      nodeEvent({
        node: "recipe_retriever_node",
        status: "failed",
        elapsed_ms: 8,
        summary: "recipe_retriever_node: failed after 8.0ms (boom).",
      }),
    ];

    render(<RunProgressTimeline events={events} phase="streaming" />);

    const summary = screen.getByText("recipe_retriever_node: failed after 8.0ms (boom).");
    expect(summary.className).toContain("text-chili");
  });

  it("shows shimmering skeleton cards while streaming", () => {
    const { container } = render(<RunProgressTimeline events={[]} phase="streaming" />);
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("shows the error message and calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    render(
      <RunProgressTimeline
        events={[]}
        phase="error"
        errorDetail="Internal Server Error"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("Internal Server Error")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("omits the retry button entirely when no onRetry is supplied", () => {
    render(<RunProgressTimeline events={[]} phase="error" errorDetail="boom" />);
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
