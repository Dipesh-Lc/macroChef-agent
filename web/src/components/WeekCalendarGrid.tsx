import { DayPlanCard, type DayPlanCardPlan } from "./DayPlanCard";
import { allDaysIdentical } from "../lib/weekPlan";

/**
 * Calendar-style grid of `DayPlanCard`s for a `WeeklyPlan`/`PublicWeeklyPlan`
 * (see those schemas' docstrings), plus the mandatory "identical days"
 * honesty callout (roadmap item, W4 task spec) -- a plain client-side
 * equality check over already-served data (`allDaysIdentical`, see
 * `lib/weekPlan.ts`), never a safety/nutrition computation. Never hides or
 * fakes variety when the corpus repeats the same day plan.
 *
 * `trustedPoolSize` is optional: `PublicWeeklyPlan` (the share-safe
 * projection) omits `trusted_pool_size` entirely (leaks how many corpus
 * recipes were available to the sharer -- see that schema's docstring), so
 * the shared-plan viewer passes nothing here and the callout's parenthetical
 * pool-size detail is simply omitted rather than guessed.
 */
export function WeekCalendarGrid({
  days,
  trustedPoolSize,
  onSelectRecipe,
}: {
  days: DayPlanCardPlan[];
  trustedPoolSize?: number;
  /** Optional -- forwarded straight through to each `DayPlanCard` (see that
   * component's own docstring for why this stays optional: the shared-plan
   * viewer doesn't wire it). */
  onSelectRecipe?: (recipeId: string) => void;
}) {
  const identical = allDaysIdentical(days);

  return (
    <section className="flex flex-col gap-3">
      {identical && (
        <div className="rounded-md border border-dashed border-honey-dark bg-honey/10 px-3 py-2 text-sm text-honey-dark">
          {trustedPoolSize != null
            ? `With the current grounded corpus (trusted pool: ${trustedPoolSize} recipes), day plans repeat — this is a known limitation, not a bug.`
            : "With the current grounded corpus, day plans repeat — this is a known limitation, not a bug."}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {days.map((day, index) => (
          <DayPlanCard key={index} dayIndex={index} plan={day} onSelectRecipe={onSelectRecipe} />
        ))}
      </div>
    </section>
  );
}
