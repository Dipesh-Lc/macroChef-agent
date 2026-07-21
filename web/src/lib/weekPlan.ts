/**
 * Pure, client-side "are all days identical" check for a `WeeklyPlan`/
 * `PublicWeeklyPlan`'s `days` list. This is deliberately NOT a safety or
 * nutrition computation -- it is a plain structural equality check over
 * already-served, already-safety-cleared data (see
 * `app.schemas.weekly_plan.WeeklyPlan`'s docstring: with the current tiny
 * grounded-recipe pool, every day is typically the exact same
 * `assemble_day_plan` call repeated, so this is expected to return `true`
 * far more often than not -- that is an honest artifact of corpus size, not
 * a bug in this function).
 *
 * "Identical" means the same multiset of `{recipe_id, servings}` pairs
 * (order-independent, since two `assemble_day_plan` calls over the same
 * candidates/target are deterministic and will list items in the same
 * order anyway, but sorting first makes the check robust to that not
 * being guaranteed).
 */

export interface DayPlanItemsLike {
  items?: { recipe_id: string; servings: number }[] | null;
}

function daySignature(day: DayPlanItemsLike): string {
  const items = day.items ?? [];
  return items
    .map((item) => `${item.recipe_id}:${item.servings}`)
    .sort()
    .join("|");
}

/**
 * `true` iff `days` has at least 2 entries and every entry has the same
 * `daySignature`. A single day (or an empty list) is never "identical" in
 * any meaningful sense -- there is nothing to compare -- so this always
 * returns `false` for `days.length < 2`, deliberately not `true` (an
 * identical-days callout would be nonsensical for a 1-day plan).
 */
export function allDaysIdentical(days: DayPlanItemsLike[]): boolean {
  if (days.length < 2) {
    return false;
  }
  const first = daySignature(days[0]);
  return days.every((day) => daySignature(day) === first);
}
