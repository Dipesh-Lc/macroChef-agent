import { describe, expect, it } from "vitest";
import {
  buildContainerTiles,
  tileColorClassForRecipeIndex,
  type ContainerPlanItemLike,
} from "./containerGrouping";

describe("buildContainerTiles", () => {
  it("expands one item into `servings` tiles for that recipe", () => {
    const items: ContainerPlanItemLike[] = [{ recipe_id: "r1", title: "Chicken Bowl", servings: 4 }];
    const tiles = buildContainerTiles(items);

    expect(tiles).toHaveLength(4);
    expect(tiles.every((tile) => tile.recipeId === "r1")).toBe(true);
    expect(tiles.map((tile) => tile.indexWithinRecipe)).toEqual([0, 1, 2, 3]);
  });

  it("sums tile count across multiple recipes to the total container count", () => {
    // Mirrors `app.services.batch_planner._distribute_containers`'s own
    // example: containers=10, R=3 -> [4, 3, 3].
    const items: ContainerPlanItemLike[] = [
      { recipe_id: "r1", title: "A", servings: 4 },
      { recipe_id: "r2", title: "B", servings: 3 },
      { recipe_id: "r3", title: "C", servings: 3 },
    ];
    const tiles = buildContainerTiles(items);

    expect(tiles).toHaveLength(10);
    const perRecipeCounts = items.map(
      (item) => tiles.filter((tile) => tile.recipeId === item.recipe_id).length,
    );
    expect(perRecipeCounts).toEqual([4, 3, 3]);
  });

  it("returns an empty tile list for an empty items list (empty trusted pool case)", () => {
    expect(buildContainerTiles([])).toEqual([]);
  });

  it("preserves items order -- tiles for the first item come first", () => {
    const items: ContainerPlanItemLike[] = [
      { recipe_id: "r1", title: "A", servings: 1 },
      { recipe_id: "r2", title: "B", servings: 1 },
    ];
    const tiles = buildContainerTiles(items);
    expect(tiles.map((tile) => tile.recipeId)).toEqual(["r1", "r2"]);
  });
});

describe("tileColorClassForRecipeIndex", () => {
  it("returns a distinct class for each of the first 5 indices", () => {
    const classes = [0, 1, 2, 3, 4].map(tileColorClassForRecipeIndex);
    expect(new Set(classes).size).toBe(5);
  });

  it("cycles back to the same class after 5 recipes (max_recipes is capped at 5 server-side)", () => {
    expect(tileColorClassForRecipeIndex(5)).toBe(tileColorClassForRecipeIndex(0));
    expect(tileColorClassForRecipeIndex(6)).toBe(tileColorClassForRecipeIndex(1));
  });

  it("never returns a class containing the reserved chili color", () => {
    for (let index = 0; index < 10; index += 1) {
      expect(tileColorClassForRecipeIndex(index)).not.toContain("chili");
    }
  });
});
