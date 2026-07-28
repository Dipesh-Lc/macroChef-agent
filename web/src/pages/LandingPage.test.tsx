import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import LandingPage from "./LandingPage";

function renderLandingPage() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LandingPage", () => {
  it("renders the hero value prop", () => {
    renderLandingPage();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /meal planning that never hides its own uncertainty/i,
      }),
    ).toBeInTheDocument();
  });

  it('"Try the planner" CTA navigates to /plan', () => {
    renderLandingPage();
    const cta = screen.getByRole("link", { name: /try the planner/i });
    expect(cta).toHaveAttribute("href", "/plan");
  });

  it('"Chat with Chef" CTA navigates to /chat (coming-soon page, not a 404)', () => {
    renderLandingPage();
    const cta = screen.getByRole("link", { name: /chat with chef/i });
    expect(cta).toHaveAttribute("href", "/chat");
  });

  it("renders the three proof chips with real numbers, not a stale hardcoded count", () => {
    renderLandingPage();
    expect(screen.getByText(/deterministic allergy safety/i)).toBeInTheDocument();
    expect(screen.getAllByText(/0 \/ 269 adjudicated violations/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/usda-grounded macros/i)).toBeInTheDocument();
    expect(screen.getByText(/watch the agent think/i)).toBeInTheDocument();
  });

  it("renders the how-it-works pipeline with the actual graph node labels, in order", () => {
    renderLandingPage();
    const labels = [
      "Intake",
      "Inventory confirmation",
      "Constraint builder",
      "Recipe retrieval",
      "Safety filter",
      "Fallback relaxation",
      "Substitution",
      "Nutrition scoring",
      "Meal ranking",
      "Procurement",
      "Memory update",
    ];
    const headings = labels.map((label) => screen.getByText(label));
    for (let i = 0; i < headings.length - 1; i += 1) {
      expect(
        headings[i].compareDocumentPosition(headings[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it("renders a footer GitHub link and an eval methodology link to the new /evals page", () => {
    renderLandingPage();
    const githubLink = screen.getByRole("link", { name: /view on github/i });
    expect(githubLink).toHaveAttribute("href", expect.stringContaining("github.com"));
    // ROADMAP 4.6: the methodology link now points at the in-app eval page
    // (previously a GitHub README anchor stand-in, since the page didn't
    // exist yet when the landing page was built).
    const methodologyLink = screen.getByRole("link", { name: /read the eval methodology/i });
    expect(methodologyLink).toHaveAttribute("href", "/evals");
  });

  it("the deterministic-allergy-safety proof chip links to the new /evals page", () => {
    renderLandingPage();
    const chip = screen.getByRole("link", { name: /deterministic allergy safety/i });
    expect(chip).toHaveAttribute("href", "/evals");
  });
});
