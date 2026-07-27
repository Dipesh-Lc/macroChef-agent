import type { ReactElement } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { Recipe, RecipeSearchResponse, ShoppingListResponse } from "../api/types";
import { getRecipe, getShoppingListForItems, searchRecipes } from "../api/endpoints";
import RecipeSearchPage from "./RecipeSearchPage";

vi.mock("../api/endpoints", async () => {
  const actual = await vi.importActual<typeof import("../api/endpoints")>("../api/endpoints");
  return {
    ...actual,
    searchRecipes: vi.fn(),
    getShoppingListForItems: vi.fn(),
    getRecipe: vi.fn(),
  };
});

function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function buildRecipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    recipe_id: "seed_1",
    title: "Search Result Recipe",
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

function buildSearchResponse(overrides: Partial<RecipeSearchResponse> = {}): RecipeSearchResponse {
  return {
    results: [buildRecipe()],
    total_matched: 1,
    macro_unavailable_excluded: 0,
    ...overrides,
  };
}

describe("RecipeSearchPage", () => {
  const mockedSearchRecipes = vi.mocked(searchRecipes);
  const mockedGetShoppingListForItems = vi.mocked(getShoppingListForItems);
  const mockedGetRecipe = vi.mocked(getRecipe);

  it("renders search results after a search", async () => {
    mockedSearchRecipes.mockResolvedValue(buildSearchResponse());

    renderWithQueryClient(<RecipeSearchPage />);

    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));

    await waitFor(() => expect(screen.getByText("Search Result Recipe")).toBeInTheDocument());
    expect(screen.getByText("Results (1)")).toBeInTheDocument();
  });

  it("surfaces macro_unavailable_excluded when nonzero", async () => {
    mockedSearchRecipes.mockResolvedValue(buildSearchResponse({ macro_unavailable_excluded: 2 }));

    renderWithQueryClient(<RecipeSearchPage />);
    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "2 recipes excluded from macro-filtered results due to incomplete nutrition data.",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("adds a search result to the plan, then removes it", async () => {
    mockedSearchRecipes.mockResolvedValue(buildSearchResponse());

    renderWithQueryClient(<RecipeSearchPage />);
    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));

    await waitFor(() => expect(screen.getByText("Search Result Recipe")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Add to plan" }));

    expect(screen.getByRole("button", { name: "In plan" })).toBeDisabled();
    // The plan panel now shows the added recipe as a clickable title.
    expect(
      screen.getAllByRole("button", { name: "Search Result Recipe" }).length,
    ).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Remove Search Result Recipe from plan" }));

    expect(screen.getByText("Add recipes from your search results to build a plan.")).toBeInTheDocument();
  });

  it("generates a shopping list from the assembled plan", async () => {
    mockedSearchRecipes.mockResolvedValue(buildSearchResponse());
    const shoppingList: ShoppingListResponse = {
      shopping_list: [{ name: "rice", amount: 200, unit: "g", quantity: null }],
    };
    mockedGetShoppingListForItems.mockResolvedValue(shoppingList);

    renderWithQueryClient(<RecipeSearchPage />);
    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));
    await waitFor(() => expect(screen.getByText("Search Result Recipe")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Add to plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate shopping list" }));

    await waitFor(() => expect(screen.getByText("Shopping list")).toBeInTheDocument());
    expect(mockedGetShoppingListForItems).toHaveBeenCalledWith({
      items: [{ recipe_id: "seed_1", title: "Search Result Recipe", servings: 1 }],
      inventory: [],
    });
    expect(screen.getByText("rice")).toBeInTheDocument();
  });

  it("opens RecipeDetailModal when a result's 'View details' is clicked", async () => {
    mockedSearchRecipes.mockResolvedValue(buildSearchResponse());
    mockedGetRecipe.mockResolvedValue(buildRecipe());

    renderWithQueryClient(<RecipeSearchPage />);
    fireEvent.click(screen.getByRole("button", { name: "Search recipes" }));
    await waitFor(() => expect(screen.getByText("Search Result Recipe")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "View details" }));

    await waitFor(() => expect(mockedGetRecipe).toHaveBeenCalledWith("seed_1"));
  });
});
