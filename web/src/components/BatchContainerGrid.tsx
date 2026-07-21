import {
  buildContainerTiles,
  tileColorClassForRecipeIndex,
  type ContainerPlanItemLike,
} from "../lib/containerGrouping";

/**
 * Visual grid of `containers` total tiles for a `BatchPlan`/
 * `PublicBatchPlan`'s `items` (see `app.schemas.batch_plan.BatchPlan`'s
 * docstring: `PlanItem.servings` IS the container count for that recipe in
 * this context, not an eating-serving count -- do not confuse with
 * `DayPlanCard`'s reading of the same field name on a `DayPlan`).
 *
 * The tile count is asserted against `containers` -- a mismatch is
 * surfaced as a visible note (never silently swallowed), even though it
 * should never happen: `assemble_batch_plan`'s `_distribute_containers`
 * always sums `items[].servings` to exactly `containers`.
 */
export function BatchContainerGrid({
  items,
  containers,
}: {
  items: ContainerPlanItemLike[];
  containers: number;
}) {
  const tiles = buildContainerTiles(items);
  const recipeIndexById = new Map(items.map((item, index) => [item.recipe_id, index]));

  if (items.length === 0) {
    return (
      <p className="text-sm text-cast-iron/70">
        No recipe could be selected for this batch plan from your currently safe, matching recipes.
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Containers</h2>

      {tiles.length !== containers && (
        <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {tiles.length} container tile{tiles.length === 1 ? "" : "s"} rendered, but {containers} were
          requested -- this indicates a mismatch between the plan's items and its container count.
        </div>
      )}

      <div className="grid grid-cols-5 gap-2 sm:grid-cols-8 lg:grid-cols-10">
        {tiles.map((tile, index) => (
          <div
            key={`${tile.recipeId}-${tile.indexWithinRecipe}`}
            title={tile.title}
            className={`flex aspect-square items-center justify-center rounded-md border text-[10px] font-mono ${tileColorClassForRecipeIndex(recipeIndexById.get(tile.recipeId) ?? index)}`}
          >
            {index + 1}
          </div>
        ))}
      </div>

      <ul className="flex flex-wrap gap-3 text-xs text-cast-iron/70">
        {items.map((item, index) => (
          <li key={item.recipe_id} className="flex items-center gap-1.5">
            <span
              className={`h-3 w-3 rounded-sm border ${tileColorClassForRecipeIndex(index)}`}
              aria-hidden="true"
            />
            <span>
              {item.title} ({item.servings} container{item.servings === 1 ? "" : "s"})
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
