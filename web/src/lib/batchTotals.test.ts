import { describe, expect, it } from "vitest";
import type { Recipe, RecipeNutrition } from "../api/types";
import { batchTotalsLine } from "../lib/batchTotals";

// Mirrors the batch-totals cases in `tests/test_serving_scaler_frontend.py`
// (`_batch_totals_line`) -- see that file for the Python source of truth.

function buildRecipe(nutrition: RecipeNutrition | null): Recipe {
  return {
    recipe_id: "r1",
    title: "Test Recipe",
    ingredients: [{ name: "chicken", amount: 150, unit: "g" }],
    instructions: ["Cook."],
    nutrition,
    servings: 1,
    source_type: "base",
    is_user_saved: false,
    is_active: true,
    restored_from_quarantine: false,
    derived_allergens: [],
  };
}

describe("batchTotalsLine", () => {
  it("multiplies per-serving macros by target servings for a grounded recipe", () => {
    const macros = { calories: 500, protein_g: 40, carbs_g: 50, fat_g: 15, fiber_g: 8 };
    const recipe = buildRecipe({
      status: "grounded",
      servings: 1,
      total: macros,
      per_serving: macros,
      contributions: [{ name: "chicken", grounded: true }],
      ungrounded_ingredients: [],
      coverage: 1.0,
      flags: [],
    });

    const line = batchTotalsLine(recipe, 4);

    expect(line).toContain("4 serving(s)");
    expect(line).toContain("2000 kcal"); // 500 * 4
    expect(line).toContain("160 g protein"); // 40 * 4
    expect(line).not.toContain("~"); // grounded is never approx-prefixed
  });

  it("approx-prefixes the line for a partial recipe", () => {
    const macros = { calories: 300, protein_g: 20, carbs_g: 30, fat_g: 8, fiber_g: 4 };
    const recipe = buildRecipe({
      status: "partial",
      servings: 1,
      total: macros,
      per_serving: macros,
      contributions: [],
      ungrounded_ingredients: ["mystery sauce"],
      coverage: 0.5,
      flags: [],
    });

    const line = batchTotalsLine(recipe, 2);

    expect(line).toContain("~");
    expect(line).toContain("600 kcal"); // 300 * 2
  });

  it("is hidden (null) when macros are unknown (no nutrition)", () => {
    expect(batchTotalsLine(buildRecipe(null), 4)).toBeNull();
  });

  it("is hidden (null) when a trust flag demotes an otherwise-grounded recipe", () => {
    const macros = { calories: 5000, protein_g: 40, carbs_g: 50, fat_g: 15, fiber_g: 8 };
    const recipe = buildRecipe({
      status: "grounded",
      servings: 1,
      total: macros,
      per_serving: macros,
      contributions: [],
      ungrounded_ingredients: [],
      coverage: 1.0,
      flags: ["implausible_kcal_per_serving"],
    });

    expect(batchTotalsLine(recipe, 4)).toBeNull();
  });
});
