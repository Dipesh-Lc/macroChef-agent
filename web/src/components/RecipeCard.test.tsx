import type { ReactElement } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { MealRecommendation, Recipe, RecipeScore } from "../api/types";
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

function buildRecommendation(recipe: Recipe): MealRecommendation {
  return { recipe, score: buildScore(), explanation: "Because reasons." };
}

describe("RecipeCard restored-from-quarantine badge", () => {
  it("shows the badge for a restored recipe", () => {
    renderWithQueryClient(
      <RecipeCard recommendation={buildRecommendation(buildRecipe({ restored_from_quarantine: true }))} />,
    );
    expect(screen.getByText("Restored from source")).toBeInTheDocument();
  });

  it("omits the badge for a normal recipe", () => {
    renderWithQueryClient(
      <RecipeCard recommendation={buildRecommendation(buildRecipe({ restored_from_quarantine: false }))} />,
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

    renderWithQueryClient(<RecipeCard recommendation={buildRecommendation(buildRecipe())} />);

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

    renderWithQueryClient(<RecipeCard recommendation={buildRecommendation(buildRecipe())} />);

    fireEvent.click(screen.getByText("Get detailed instructions"));

    await waitFor(() =>
      expect(
        screen.getByText("Could not generate detailed instructions. Please try again."),
      ).toBeInTheDocument(),
    );
  });
});
