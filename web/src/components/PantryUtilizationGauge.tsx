import { formatPercent } from "../lib/format";

/**
 * `WeeklyPlan.pantry_utilization` / `uncompared_ingredient_count` display
 * (see `app.schemas.weekly_plan.WeeklyPlan`'s docstring) -- reuses
 * `NutritionBreakdown.tsx`'s `CoverageBar` visual pattern (a labeled basil
 * progress bar over `sage-line`), but this is a SEPARATE metric: pantry
 * coverage of the week's ingredient need, never USDA grounding coverage.
 *
 * REPORTED FOR VISIBILITY ONLY (mirrors the Python docstring verbatim):
 * this component only renders the number, it never implies the value was
 * optimized or maximized -- `pantry_utilization` never gates or selects
 * which recipes were chosen.
 */
export function PantryUtilizationGauge({
  utilization,
  uncomparedCount,
}: {
  utilization: number;
  uncomparedCount: number;
}) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Pantry utilization</h2>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between text-xs text-cast-iron/60">
          <span>Share of this week's ingredient need already in your pantry</span>
          <span className="font-mono">{formatPercent(utilization)}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-sage-line">
          <div
            className="h-full rounded-full bg-basil"
            style={{ width: `${Math.round(utilization * 100)}%` }}
          />
        </div>
      </div>
      <p className="text-xs text-cast-iron/60">
        {uncomparedCount} ingredient{uncomparedCount === 1 ? "" : "s"} couldn't be compared by weight —
        excluded, not guessed.
      </p>
    </section>
  );
}
