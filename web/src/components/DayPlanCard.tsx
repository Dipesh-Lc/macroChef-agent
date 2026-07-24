/**
 * Compact, single-day card for the week-plan calendar grid
 * (`WeekCalendarGrid.tsx`) -- a deliberately lighter variant of
 * `PlanMacroSummary` (which renders all five macros with full target rows):
 * showing 7 (or up to 14) full `PlanMacroSummary` copies side by side would
 * be overwhelming, so this shows only what the task spec calls out as the
 * minimum -- total calories/protein plus the `within_tolerance` state --
 * plus the day's meal list, using the SAME provenance grammar
 * (`within_tolerance` solid-basil/dashed-honey) as `PlanMacroSummary`,
 * driven entirely by the already-computed flag, never a new fit decision
 * made here.
 *
 * Structurally compatible with both `DayPlan` and `PublicDayPlan` (the
 * share-safe projection) -- this component reads nothing that isn't present
 * on both.
 */
export interface DayPlanCardPlan {
  items?: { recipe_id: string; title: string; servings: number }[] | null;
  total_calories: number;
  total_protein_g: number;
  target_calories: number;
  target_protein_g: number;
  within_tolerance: boolean;
}

export function DayPlanCard({
  dayIndex,
  plan,
  onSelectRecipe,
}: {
  dayIndex: number;
  plan: DayPlanCardPlan;
  /** Optional -- the shared-plan viewer (a `PublicDayPlan`, no session/API
   * access) doesn't wire this, so a recipe title there is inert text, not a
   * click target. See `WeekPlanPage.tsx`, which lifts the single
   * `selectedRecipeId` state up to the page level (one modal instance for
   * the whole week grid, not one per card). */
  onSelectRecipe?: (recipeId: string) => void;
}) {
  const items = plan.items ?? [];
  return (
    <article className="flex flex-col gap-2 rounded-lg border border-sage-line bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-sm font-semibold text-cast-iron">Day {dayIndex + 1}</h3>
        {plan.within_tolerance ? (
          <span className="rounded-full border border-basil px-2 py-0.5 text-xs font-medium text-basil">
            Within tolerance
          </span>
        ) : (
          <span className="rounded-full border border-dashed border-honey-dark px-2 py-0.5 text-xs font-medium text-honey-dark">
            Closest found
          </span>
        )}
      </div>

      <p className="font-mono text-xs text-cast-iron/70">
        {Math.round(plan.total_calories)} / {Math.round(plan.target_calories)} kcal ·{" "}
        {Math.round(plan.total_protein_g)} / {Math.round(plan.target_protein_g)}g protein
      </p>

      {items.length === 0 ? (
        <p className="text-xs text-cast-iron/60">No feasible meals for this day.</p>
      ) : (
        <ul className="flex flex-col gap-0.5 text-xs text-cast-iron">
          {items.map((item) => (
            <li key={item.recipe_id} className="flex items-center justify-between gap-2">
              {onSelectRecipe ? (
                <button
                  type="button"
                  onClick={() => onSelectRecipe(item.recipe_id)}
                  className="truncate text-left underline-offset-2 hover:underline"
                >
                  {item.title}
                </button>
              ) : (
                <span className="truncate">{item.title}</span>
              )}
              <span className="shrink-0 font-mono text-cast-iron/60">
                {item.servings}x
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
