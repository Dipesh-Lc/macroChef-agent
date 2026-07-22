import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TasteProfilePanel } from "./TasteProfilePanel";

// Backfills the coverage gap left by deleting
// tests/test_taste_profile_frontend.py (Streamlit's `taste_profile_markup`)
// -- see docs/BACKLOG.md's SPA W6 entry. Ported cases: both-lists-shown,
// avoided-only, preferred-only, and the "not enough signal yet" empty
// states (empty lists / missing profile). Escaping is not re-tested here
// for the same structural reason documented in WasteNudges.test.tsx.

describe("TasteProfilePanel", () => {
  it("shows both avoided ingredients and preferred cuisines when both are present", () => {
    render(
      <TasteProfilePanel
        tasteProfile={{ avoided_ingredients: ["cilantro"], preferred_cuisines: ["Italian"] }}
      />,
    );
    expect(screen.getByText("cilantro")).toBeInTheDocument();
    expect(screen.getByText("Italian")).toBeInTheDocument();
  });

  it("shows only avoided ingredients when there is no cuisine drift", () => {
    const { container } = render(
      <TasteProfilePanel tasteProfile={{ avoided_ingredients: ["cilantro"], preferred_cuisines: [] }} />,
    );
    expect(screen.getByText("cilantro")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Drifting toward");
  });

  it("shows only preferred cuisines when there are no avoided ingredients", () => {
    const { container } = render(
      <TasteProfilePanel tasteProfile={{ avoided_ingredients: [], preferred_cuisines: ["Thai"] }} />,
    );
    expect(screen.getByText("Thai")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Auto-avoided");
  });

  it("renders nothing when neither list has a signal yet", () => {
    const { container } = render(
      <TasteProfilePanel tasteProfile={{ avoided_ingredients: [], preferred_cuisines: [] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the taste profile is missing entirely", () => {
    const { container: nullContainer } = render(<TasteProfilePanel tasteProfile={null} />);
    expect(nullContainer).toBeEmptyDOMElement();

    const { container: undefinedContainer } = render(<TasteProfilePanel tasteProfile={undefined} />);
    expect(undefinedContainer).toBeEmptyDOMElement();
  });

  it("never renders a malicious ingredient/cuisine name as live markup", () => {
    const { container } = render(
      <TasteProfilePanel
        tasteProfile={{ avoided_ingredients: ["<script>alert(1)</script>"], preferred_cuisines: [] }}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });
});
