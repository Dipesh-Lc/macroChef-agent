/**
 * Pure container-tile grouping math for a `BatchPlan`/`PublicBatchPlan`'s
 * `items`. `PlanItem.servings` is reused AS the container count for that
 * recipe in a batch-plan context (see `app.schemas.batch_plan.BatchPlan`'s
 * docstring) -- NOT eating-servings, unlike `DayPlan.items`. This module
 * expands that into one tile per whole container so the UI can render a
 * visual grid, without ever touching nutrition or safety.
 */

export interface ContainerPlanItemLike {
  recipe_id: string;
  title: string;
  servings: number;
}

export interface ContainerTile {
  recipeId: string;
  title: string;
  /** Index of this tile within its own recipe's run (0-based) -- purely for
   * a stable React key, not a display value. */
  indexWithinRecipe: number;
}

/**
 * Expands `items` (one entry per selected recipe) into one tile per whole
 * container, in `items` order, `servings` tiles per recipe. Never
 * fabricates a fractional tile -- `servings` is always a whole container
 * count (see `app.services.batch_planner._distribute_containers`'s
 * docstring).
 */
export function buildContainerTiles(items: ContainerPlanItemLike[]): ContainerTile[] {
  const tiles: ContainerTile[] = [];
  for (const item of items) {
    for (let index = 0; index < item.servings; index += 1) {
      tiles.push({ recipeId: item.recipe_id, title: item.title, indexWithinRecipe: index });
    }
  }
  return tiles;
}

/**
 * A fixed, small palette of Tailwind class strings for coloring tiles by
 * recipe, cycling by index -- deliberately excludes `chili` (reserved
 * elsewhere in the design system for the safety-audit/danger grammar, never
 * reused as a plain categorical color -- see `SafetyAuditPanel.tsx`).
 * `max_recipes` is capped at 5 server-side (`BatchPlanRequest.max_recipes`),
 * so a 5-entry palette never has to repeat within one plan.
 */
const TILE_COLOR_CLASSES = [
  "border-basil bg-basil/15 text-basil",
  "border-honey-dark bg-honey/20 text-honey-dark",
  "border-cast-iron bg-cast-iron/10 text-cast-iron",
  "border-basil-dark bg-basil-dark/15 text-basil-dark",
  "border-sage-line bg-sage-line text-cast-iron/70",
] as const;

export function tileColorClassForRecipeIndex(recipeIndex: number): string {
  const length = TILE_COLOR_CLASSES.length;
  const normalized = ((recipeIndex % length) + length) % length;
  return TILE_COLOR_CLASSES[normalized];
}
