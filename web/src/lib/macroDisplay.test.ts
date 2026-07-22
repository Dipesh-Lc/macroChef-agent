import { describe, expect, it } from "vitest";
import type { FoodMacros, GroundingStatus, Recipe, RecipeNutrition } from "../api/types";
import { macroDisplay, macroDisplayState, trustedPerServing } from "./macroDisplay";

// Mirrors tests/test_nutrition_view.py's `_nutrition`/`_recipe` helpers and
// every one of its test cases -- see that file for the Python source of
// truth this module ports.

function buildNutrition(
  status: GroundingStatus,
  macros: FoodMacros,
  flags: string[] = [],
): RecipeNutrition {
  return {
    status,
    servings: 1,
    total: macros,
    per_serving: macros,
    coverage: status === "grounded" ? 1.0 : 0.5,
    flags,
    contributions: [],
    ungrounded_ingredients: [],
  };
}

function buildRecipe(nutrition: RecipeNutrition | null): Recipe {
  return {
    recipe_id: "r",
    title: "Test Recipe",
    ingredients: [],
    instructions: ["Cook."],
    nutrition,
    servings: 1,
    source_type: "base",
    is_user_saved: false,
    is_active: true,
    restored_from_quarantine: false,
  };
}

describe("macroDisplayState / trustedPerServing", () => {
  it("no nutrition is unknown", () => {
    const recipe = buildRecipe(null);
    expect(macroDisplayState(recipe)).toBe("unknown");
    expect(trustedPerServing(recipe)).toBeNull();
  });

  it("grounded with no flags is trusted", () => {
    const nutrition = buildNutrition("grounded", {
      calories: 500,
      protein_g: 40,
      carbs_g: 50,
      fat_g: 15,
      fiber_g: 8,
    });
    const recipe = buildRecipe(nutrition);

    expect(macroDisplayState(recipe)).toBe("grounded");
    expect(trustedPerServing(recipe)).toEqual(nutrition.per_serving);
  });

  it("partial is displayed but never trusted for scoring", () => {
    const nutrition = buildNutrition("partial", {
      calories: 300,
      protein_g: 20,
      carbs_g: 30,
      fat_g: 8,
      fiber_g: 4,
    });
    const recipe = buildRecipe(nutrition);

    expect(macroDisplayState(recipe)).toBe("partial");
    expect(trustedPerServing(recipe)).toBeNull();
  });

  it("ungrounded is unknown", () => {
    const nutrition = buildNutrition("ungrounded", {
      calories: 0,
      protein_g: 0,
      carbs_g: 0,
      fat_g: 0,
      fiber_g: 0,
    });
    const recipe = buildRecipe(nutrition);

    expect(macroDisplayState(recipe)).toBe("unknown");
    expect(trustedPerServing(recipe)).toBeNull();
  });

  it("flagged grounded recipe demotes to unknown and untrusted", () => {
    // The core assertion this module exists to preserve: a demoting flag
    // overrides "grounded" status for both display and trust, even though
    // every ingredient grounded -- an implausible computed value is not
    // more trustworthy just because coverage is complete.
    const nutrition = buildNutrition(
      "grounded",
      { calories: 5000, protein_g: 40, carbs_g: 50, fat_g: 15, fiber_g: 8 },
      ["implausible_kcal_per_serving"],
    );
    const recipe = buildRecipe(nutrition);

    expect(macroDisplayState(recipe)).toBe("unknown");
    expect(trustedPerServing(recipe)).toBeNull();
  });

  it("flagged partial recipe stays unknown, not partial", () => {
    // Conservative interpretation ported from the Python test: a demoting
    // flag applies regardless of status, not only when status happens to
    // be "grounded".
    const nutrition = buildNutrition(
      "partial",
      { calories: 5000, protein_g: 40, carbs_g: 50, fat_g: 15, fiber_g: 8 },
      ["implausible_kcal_per_serving"],
    );
    const recipe = buildRecipe(nutrition);

    expect(macroDisplayState(recipe)).toBe("unknown");
    expect(trustedPerServing(recipe)).toBeNull();
  });
});

describe("macroDisplay badge text (port of frontend/components/recommendation_cards.py's _macro_badge)", () => {
  it("unknown shows no numbers at all", () => {
    const recipe = buildRecipe(null);
    expect(macroDisplay(recipe)).toEqual({ state: "unknown", badgeText: "Macros unknown" });
  });

  it("grounded renders kcal/P/C/F with no USDA-matched count segment", () => {
    const nutrition = buildNutrition("grounded", {
      calories: 500,
      protein_g: 40,
      carbs_g: 50,
      fat_g: 15,
      fiber_g: 8,
    });
    nutrition.contributions = [
      { name: "chicken", grounded: true },
      { name: "rice", grounded: true },
      { name: "mystery sauce", grounded: false },
    ];
    const recipe = buildRecipe(nutrition);

    const display = macroDisplay(recipe);
    expect(display.state).toBe("grounded");
    expect(display.badgeText).toBe("500 kcal | 40P / 50C / 15F");
  });

  it("partial renders the approx-prefix + coverage % + undercounts wording", () => {
    const nutrition = buildNutrition("partial", {
      calories: 300,
      protein_g: 20,
      carbs_g: 30,
      fat_g: 8,
      fiber_g: 4,
    });
    const recipe = buildRecipe(nutrition);

    const display = macroDisplay(recipe);
    expect(display.state).toBe("partial");
    expect(display.badgeText).toBe("~300 kcal | 20P / 30C / 8F (partial, 50% grounded, likely undercounts)");
  });
});
