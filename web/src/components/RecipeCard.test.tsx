import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MealRecommendation, Recipe, RecipeScore } from "../api/types";
import { RecipeCard } from "./RecipeCard";

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
    render(<RecipeCard recommendation={buildRecommendation(buildRecipe({ restored_from_quarantine: true }))} />);
    expect(screen.getByText("Restored from source")).toBeInTheDocument();
  });

  it("omits the badge for a normal recipe", () => {
    render(<RecipeCard recommendation={buildRecommendation(buildRecipe({ restored_from_quarantine: false }))} />);
    expect(screen.queryByText("Restored from source")).toBeNull();
  });
});
