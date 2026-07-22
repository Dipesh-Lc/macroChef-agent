import { describe, expect, it } from "vitest";
import { allDaysIdentical, type DayPlanItemsLike } from "./weekPlan";

describe("allDaysIdentical", () => {
  it("is false for an empty list", () => {
    expect(allDaysIdentical([])).toBe(false);
  });

  it("is false for a single day (nothing to compare)", () => {
    const days: DayPlanItemsLike[] = [{ items: [{ recipe_id: "r1", servings: 2 }] }];
    expect(allDaysIdentical(days)).toBe(false);
  });

  it("is true when every day has the exact same recipe_id/servings set", () => {
    const days: DayPlanItemsLike[] = [
      { items: [{ recipe_id: "r1", servings: 2 }, { recipe_id: "r2", servings: 1 }] },
      { items: [{ recipe_id: "r1", servings: 2 }, { recipe_id: "r2", servings: 1 }] },
      { items: [{ recipe_id: "r1", servings: 2 }, { recipe_id: "r2", servings: 1 }] },
    ];
    expect(allDaysIdentical(days)).toBe(true);
  });

  it("is order-independent within a day", () => {
    const days: DayPlanItemsLike[] = [
      { items: [{ recipe_id: "r1", servings: 2 }, { recipe_id: "r2", servings: 1 }] },
      { items: [{ recipe_id: "r2", servings: 1 }, { recipe_id: "r1", servings: 2 }] },
    ];
    expect(allDaysIdentical(days)).toBe(true);
  });

  it("is false when a servings count differs on one day", () => {
    const days: DayPlanItemsLike[] = [
      { items: [{ recipe_id: "r1", servings: 2 }] },
      { items: [{ recipe_id: "r1", servings: 3 }] },
    ];
    expect(allDaysIdentical(days)).toBe(false);
  });

  it("is false when a recipe_id differs on one day", () => {
    const days: DayPlanItemsLike[] = [
      { items: [{ recipe_id: "r1", servings: 2 }] },
      { items: [{ recipe_id: "r9", servings: 2 }] },
    ];
    expect(allDaysIdentical(days)).toBe(false);
  });

  it("treats missing/empty items as identical to each other", () => {
    const days: DayPlanItemsLike[] = [{ items: [] }, { items: undefined }, {}];
    expect(allDaysIdentical(days)).toBe(true);
  });
});
