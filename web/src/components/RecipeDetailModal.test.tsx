import type { ReactElement } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { Recipe } from "../api/types";
import { getRecipe } from "../api/endpoints";
import { ApiError } from "../api/client";
import { RecipeDetailModal } from "./RecipeDetailModal";

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    getRecipe: vi.fn(),
  };
});

function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function buildRecipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    recipe_id: "seed_1",
    title: "Fetched Recipe",
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

describe("RecipeDetailModal", () => {
  const mockedGetRecipe = vi.mocked(getRecipe);

  it("shows a loading state, then renders the fetched recipe", async () => {
    let resolvePromise: (value: Recipe) => void;
    mockedGetRecipe.mockReturnValue(
      new Promise((resolve) => {
        resolvePromise = resolve;
      }),
    );

    renderWithQueryClient(<RecipeDetailModal recipeId="seed_1" onClose={vi.fn()} />);

    expect(screen.getByText("Loading recipe details…")).toBeInTheDocument();

    resolvePromise!(buildRecipe());

    await waitFor(() => expect(screen.getByText("Fetched Recipe")).toBeInTheDocument());
    expect(screen.queryByText("Loading recipe details…")).toBeNull();
  });

  it("shows an error state when the fetch fails", async () => {
    mockedGetRecipe.mockRejectedValue(new ApiError(404, "Recipe not found"));

    renderWithQueryClient(<RecipeDetailModal recipeId="unknown" onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Recipe not found")).toBeInTheDocument());
  });
});
