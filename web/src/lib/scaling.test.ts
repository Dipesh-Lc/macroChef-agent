import { describe, expect, it } from "vitest";
import type { Ingredient } from "../api/types";
import { ingredientDisplay, scaleIngredients } from "./scaling";

// Mirrors `tests/test_serving_scaler.py`'s cases one-for-one -- see that
// file (`app.schemas.ingredient.scale_ingredients`) for the Python source
// of truth this module ports.

describe("scaleIngredients", () => {
  it("scale factor one is a no-op", () => {
    const ingredients: Ingredient[] = [{ name: "chicken breast", amount: 150, unit: "g" }];
    const scaled = scaleIngredients(ingredients, 1.0);

    expect(scaled).toEqual(ingredients);
    expect(scaled).not.toBe(ingredients); // new list, not the same reference
    expect(scaled[0]).not.toBe(ingredients[0]); // new objects, not the same references
  });

  it("scale factor two doubles amount", () => {
    const ingredients: Ingredient[] = [{ name: "rice", amount: 100, unit: "g" }];
    const scaled = scaleIngredients(ingredients, 2.0);

    expect(scaled[0].amount).toBe(200);
    expect(scaled[0].name).toBe("rice");
    expect(scaled[0].unit).toBe("g");
  });

  it("scale factor half halves amount", () => {
    const ingredients: Ingredient[] = [{ name: "olive oil", amount: 2, unit: "tbsp" }];
    const scaled = scaleIngredients(ingredients, 0.5);

    expect(scaled[0].amount).toBe(1);
  });

  it("none amount is never fabricated", () => {
    const ingredients: Ingredient[] = [{ name: "salt to taste", amount: null, unit: null }];
    const scaled = scaleIngredients(ingredients, 3.0);

    expect(scaled[0].amount).toBeNull();
    expect(scaled[0].name).toBe("salt to taste");
  });

  it("unit, name, and preparation are preserved", () => {
    const ingredients: Ingredient[] = [
      { name: "rice", amount: 150, unit: "g", preparation: "cooked" },
    ];
    const scaled = scaleIngredients(ingredients, 4.0);

    expect(scaled[0].unit).toBe("g");
    expect(scaled[0].preparation).toBe("cooked");
    expect(scaled[0].amount).toBe(600);
  });

  it("empty list returns empty list", () => {
    expect(scaleIngredients([], 2.0)).toEqual([]);
  });
});

describe("ingredientDisplay (port of Ingredient.display())", () => {
  it("renders amount + unit + name when amount is set", () => {
    expect(ingredientDisplay({ name: "rice", amount: 200, unit: "g" })).toBe("200 g rice");
  });

  it("renders the bare name when amount is missing -- never fabricates a quantity", () => {
    const rendered = ingredientDisplay({ name: "salt to taste", amount: null, unit: null });
    expect(rendered).toBe("salt to taste");
    expect(rendered).not.toContain("null");
  });

  it("omits the unit segment when unit is missing", () => {
    expect(ingredientDisplay({ name: "eggs", amount: 2, unit: null })).toBe("2 eggs");
  });
});
