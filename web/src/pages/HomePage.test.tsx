import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MealRecommendation, Recipe, RecipeScore, RecommendationResponse } from "../api/types";
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

import { recommendRecipes } from "../api/endpoints";

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

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(recommendRecipes).mockReset();
});

describe("HomePage See more pagination", () => {
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
