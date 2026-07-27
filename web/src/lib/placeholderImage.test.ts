import { describe, expect, it } from "vitest";
import { RECIPE_ART_GRADIENTS, hashString, recipeArt } from "./placeholderImage";

describe("recipeArt determinism", () => {
  it("returns the same gradient + icon for the same title/cuisine every call", () => {
    const recipe = { title: "Peanut Butter Chicken Satay", cuisine: "Thai" };
    const first = recipeArt(recipe);
    const second = recipeArt(recipe);
    const third = recipeArt({ ...recipe });

    expect(second).toEqual(first);
    expect(third).toEqual(first);
  });

  it("stays deterministic across repeated calls for a recipe with no cuisine", () => {
    const recipe = { title: "Mystery Fridge Stir-Fry", cuisine: null };
    expect(recipeArt(recipe)).toEqual(recipeArt(recipe));
  });

  it("falls back to fixed seed strings instead of throwing for empty fields", () => {
    expect(() => recipeArt({ title: "", cuisine: null })).not.toThrow();
    const first = recipeArt({ title: "", cuisine: null });
    const second = recipeArt({ title: "", cuisine: null });
    expect(second).toEqual(first);
  });

  it("picks a gradient that exists in the fixed design-token palette", () => {
    const { gradient } = recipeArt({ title: "Any Recipe", cuisine: "Any" });
    expect(RECIPE_ART_GRADIENTS).toContainEqual(gradient);
  });

  it("produces different art for recipes with different titles/cuisines (no universal collision)", () => {
    const a = recipeArt({ title: "Recipe A", cuisine: "Mexican" });
    const b = recipeArt({ title: "Recipe B", cuisine: "Japanese" });
    // Not guaranteed to differ for every pair by pigeonhole, but these two
    // seeds are chosen to land in different buckets -- pins that the hash
    // isn't a constant function.
    expect(a).not.toEqual(b);
  });
});

describe("hashString", () => {
  it("is a pure, deterministic function of its input", () => {
    expect(hashString("same-seed")).toBe(hashString("same-seed"));
  });

  it("returns a non-negative integer", () => {
    const hash = hashString("anything, really");
    expect(Number.isInteger(hash)).toBe(true);
    expect(hash).toBeGreaterThanOrEqual(0);
  });
});
