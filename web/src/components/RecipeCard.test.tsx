import type { ReactElement } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { Recipe, RecipeScore } from "../api/types";
import { RecipeCard } from "./RecipeCard";
import { getDetailedInstructions } from "../api/endpoints";
import { ApiError } from "../api/client";

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getDetailedInstructions: vi.fn(),
    postFeedback: vi.fn(),
  };
});

function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

// Backfills the coverage gap left by deleting
// tests/test_restored_badge_frontend.py (Streamlit's `_restored_badge`) --
// see docs/BACKLOG.md's SPA W6 entry. The underlying flag
// (`Recipe.restored_from_quarantine`) is still set deterministically at
// load time (`app.rag.loaders.attach_restoration`, covered by
// `tests/test_loaders.py`); this only covers that `RecipeCard` renders the
// badge conditionally on it, same as the Streamlit predecessor did.

function buildRecipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    recipe_id: "imp_1",
    title: "Test Recipe",
    ingredients: [],
    instructions: ["Cook."],
    nutrition: null,
    servings: 1,
    source_type: "imported",
    is_user_saved: false,
    is_active: true,
    restored_from_quarantine: false,
    derived_allergens: [],
    ...overrides,
  };
}

function buildScore(): RecipeScore {
  return {
    recipe_id: "imp_1",
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

describe("RecipeCard: no explanation paragraph, no trust badge/USDA-matched text", () => {
  it("never renders the LLM-generated explanation text", () => {
    renderWithQueryClient(
      <RecipeCard recipe={buildRecipe()} score={buildScore()} explanation="Because reasons." />,
    );
    expect(screen.queryByText("Because reasons.")).toBeNull();
  });

  it("never renders a TrustBadge state label or USDA-matched count text", () => {
    renderWithQueryClient(<RecipeCard recipe={buildRecipe()} score={buildScore()} />);
    expect(screen.queryByText("USDA ✓")).toBeNull();
    expect(screen.queryByText("unverified")).toBeNull();
    expect(screen.queryByText(/ingredients USDA-matched/)).toBeNull();
  });
});

describe("RecipeCard: Matching Info chips are always visible", () => {
  it("renders used/missing ingredient chips unconditionally, before the score-details toggle", () => {
    const recipe = buildRecipe();
    const score = { ...buildScore(), used_ingredients: ["chicken"], missing_ingredients: ["rice"] };
    renderWithQueryClient(<RecipeCard recipe={recipe} score={score} />);

    expect(screen.getByText("Matching Info")).toBeInTheDocument();
    const chicken = screen.getByText("chicken");
    const rice = screen.getByText("rice");
    const toggle = screen.getByText("Show score details");
    expect(chicken).toBeInTheDocument();
    expect(rice).toBeInTheDocument();

    // DOM order: chips appear before the score-details toggle.
    expect(
      chicken.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

describe("RecipeCard: score-details toggle", () => {
  it("hides the 5 remaining score tiles until 'Show score details' is clicked", () => {
    renderWithQueryClient(<RecipeCard recipe={buildRecipe()} score={buildScore()} />);

    expect(screen.queryByText("Final")).toBeNull();
    expect(screen.queryByText("Macros")).toBeNull();
    expect(screen.queryByText("Time")).toBeNull();
    expect(screen.queryByText("Preference")).toBeNull();
    expect(screen.queryByText("Pantry mass")).toBeNull();
    // The redundant "Pantry" tile was dropped entirely (chips already cover it).
    expect(screen.queryByText("Pantry")).toBeNull();

    fireEvent.click(screen.getByText("Show score details"));

    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(screen.getByText("Macros")).toBeInTheDocument();
    expect(screen.getByText("Time")).toBeInTheDocument();
    expect(screen.getByText("Preference")).toBeInTheDocument();
    expect(screen.getByText("Pantry mass")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Hide score details"));

    expect(screen.queryByText("Final")).toBeNull();
  });
});

describe("RecipeCard restored-from-quarantine badge", () => {
  it("shows the badge for a restored recipe", () => {
    renderWithQueryClient(
      <RecipeCard recipe={buildRecipe({ restored_from_quarantine: true })} score={buildScore()} />,
    );
    expect(screen.getByText("Restored from source")).toBeInTheDocument();
  });

  it("omits the badge for a normal recipe", () => {
    renderWithQueryClient(
      <RecipeCard recipe={buildRecipe({ restored_from_quarantine: false })} score={buildScore()} />,
    );
    expect(screen.queryByText("Restored from source")).toBeNull();
  });
});

describe("RecipeCard 'Get detailed instructions'", () => {
  const mockedGetDetailedInstructions = vi.mocked(getDetailedInstructions);

  it("shows a loading state, then renders the returned steps", async () => {
    let resolvePromise: (value: Awaited<ReturnType<typeof getDetailedInstructions>>) => void;
    mockedGetDetailedInstructions.mockReturnValue(
      new Promise((resolve) => {
        resolvePromise = resolve;
      }),
    );

    renderWithQueryClient(<RecipeCard recipe={buildRecipe()} score={buildScore()} />);

    fireEvent.click(screen.getByText("Get detailed instructions"));

    expect(await screen.findByText("Generating…")).toBeInTheDocument();

    resolvePromise!({
      steps: ["Preheat the oven to 400F.", "Bake for 20 minutes until golden."],
      generated: true,
      provider_note: null,
    });

    await waitFor(() => expect(screen.getByText("Detailed steps")).toBeInTheDocument());
    expect(screen.getByText("Preheat the oven to 400F.")).toBeInTheDocument();
    expect(screen.getByText("Bake for 20 minutes until golden.")).toBeInTheDocument();
  });

  it("handles an error response gracefully, without crashing", async () => {
    mockedGetDetailedInstructions.mockRejectedValue(
      new ApiError(500, "Could not generate detailed instructions. Please try again."),
    );

    renderWithQueryClient(<RecipeCard recipe={buildRecipe()} score={buildScore()} />);

    fireEvent.click(screen.getByText("Get detailed instructions"));

    await waitFor(() =>
      expect(
        screen.getByText("Could not generate detailed instructions. Please try again."),
      ).toBeInTheDocument(),
    );
  });
});

describe("RecipeCard: recipe art never clips the title (ROADMAP 4.4)", () => {
  it("renders the full title as normal DOM text, never truncated/clipped by CSS", () => {
    const longTitle =
      "Slow-Braised Grandma's Sunday Pot Roast with Root Vegetables, Fresh Herbs, and a Red Wine Pan Sauce";
    renderWithQueryClient(<RecipeCard recipe={buildRecipe({ title: longTitle })} score={buildScore()} />);

    const heading = screen.getByText(longTitle);
    expect(heading).toBeInTheDocument();
    expect(heading.tagName).toBe("H3");
    // No truncation utility classes -- the title must wrap, never clip.
    expect(heading.className).not.toMatch(/truncate|line-clamp|overflow-hidden|whitespace-nowrap/);
  });

  it("renders generated art (no <img>, no remote network URL) for the card thumbnail", () => {
    const { container } = renderWithQueryClient(
      <RecipeCard recipe={buildRecipe({ title: "Any Recipe", cuisine: "Any" })} score={buildScore()} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull();
  });
});

describe("RecipeCard: without a score (plain recipe-detail view)", () => {
  it("renders base sections but omits every score-dependent section", () => {
    renderWithQueryClient(<RecipeCard recipe={buildRecipe()} />);

    // Base sections still render.
    expect(screen.getByText("Test Recipe")).toBeInTheDocument();
    expect(screen.getByText("Servings")).toBeInTheDocument();
    expect(screen.getByText("Where these numbers come from")).toBeInTheDocument();
    expect(screen.getByText("Show instructions")).toBeInTheDocument();
    expect(screen.getByText("Get detailed instructions")).toBeInTheDocument();

    // Score-dependent sections are absent.
    expect(screen.queryByText("Matching Info")).toBeNull();
    expect(screen.queryByText("Show score details")).toBeNull();
  });
});
