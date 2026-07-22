import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WasteNudge } from "../api/types";
import { WasteNudges } from "./WasteNudges";

// Backfills the coverage gap left by deleting
// tests/test_waste_nudge_frontend.py (Streamlit's `waste_nudge_markup`) --
// see docs/BACKLOG.md's SPA W6 entry for the parity mapping. Ported cases:
// timing phrases (today/tomorrow/in N days), "N way(s)" pluralization, the
// no-suggestions fallback line, and rendering multiple nudges. Escaping is
// NOT re-tested here: React always escapes text children, and
// `dangerouslySetInnerHTML` is an ESLint `error` repo-wide
// (`web/eslint.config.js`), so the XSS class of bug this component's
// Streamlit predecessor needed a dedicated regression test for is
// structurally impossible in this stack.

function nudge(overrides: Partial<WasteNudge> = {}): WasteNudge {
  return {
    ingredient_name: "spinach",
    days_until_expiry: null,
    suggested_recipes: [],
    ...overrides,
  };
}

describe("WasteNudges", () => {
  it("renders nothing when there are no nudges", () => {
    const { container } = render(<WasteNudges nudges={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when nudges is undefined", () => {
    const { container } = render(<WasteNudges nudges={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the ingredient name and suggested recipe titles", () => {
    render(
      <WasteNudges
        nudges={[
          nudge({
            days_until_expiry: 0,
            suggested_recipes: [
              { recipe_id: "r1", title: "Spinach Frittata" },
              { recipe_id: "r2", title: "Spinach Feta Pie" },
            ],
          }),
        ]}
      />,
    );

    expect(screen.getByText(/spinach/)).toBeInTheDocument();
    expect(screen.getByText("Spinach Frittata")).toBeInTheDocument();
    expect(screen.getByText("Spinach Feta Pie")).toBeInTheDocument();
    expect(screen.getByText(/2 ways/)).toBeInTheDocument();
  });

  it("uses 'today' phrasing for zero, negative, or missing days", () => {
    render(<WasteNudges nudges={[nudge({ ingredient_name: "a", days_until_expiry: 0 })]} />);
    expect(screen.getByText(/today/)).toBeInTheDocument();

    render(<WasteNudges nudges={[nudge({ ingredient_name: "b", days_until_expiry: null })]} />);
    expect(screen.getAllByText(/today/).length).toBeGreaterThan(0);

    render(<WasteNudges nudges={[nudge({ ingredient_name: "c", days_until_expiry: -2 })]} />);
    expect(screen.getAllByText(/today/).length).toBeGreaterThan(0);
  });

  it("uses 'tomorrow' phrasing for exactly one day", () => {
    render(<WasteNudges nudges={[nudge({ days_until_expiry: 1 })]} />);
    expect(screen.getByText(/tomorrow/)).toBeInTheDocument();
  });

  it("uses 'in N days' phrasing for multiple days", () => {
    render(<WasteNudges nudges={[nudge({ days_until_expiry: 3 })]} />);
    expect(screen.getByText(/in 3 days/)).toBeInTheDocument();
  });

  it("singularizes '1 way' and omits the ways count entirely with no suggestions", () => {
    render(
      <WasteNudges
        nudges={[nudge({ suggested_recipes: [{ recipe_id: "r1", title: "Recipe One" }] })]}
      />,
    );
    expect(screen.getByText(/1 way\b/)).toBeInTheDocument();

    const { container } = render(<WasteNudges nudges={[nudge({ suggested_recipes: [] })]} />);
    expect(container.textContent).not.toMatch(/\bway\b/);
    expect(screen.getByText("No recipe suggestions found in the corpus yet.")).toBeInTheDocument();
  });

  it("renders every nudge in a multi-nudge list", () => {
    render(<WasteNudges nudges={[nudge({ ingredient_name: "spinach" }), nudge({ ingredient_name: "basil" })]} />);
    expect(screen.getByText(/spinach/)).toBeInTheDocument();
    expect(screen.getByText(/basil/)).toBeInTheDocument();
  });

  it("never renders a malicious ingredient/recipe name as live markup (React auto-escapes text children)", () => {
    const { container } = render(
      <WasteNudges
        nudges={[
          nudge({
            ingredient_name: "<script>alert(1)</script>",
            suggested_recipes: [{ recipe_id: "r1", title: "<img src=x onerror=alert(1)>" }],
          }),
        ]}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });
});
