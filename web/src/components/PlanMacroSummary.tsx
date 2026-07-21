/**
 * All-five-macros parity view for `app.schemas.day_plan.DayPlan` (and its
 * share-safe projection, `PublicDayPlan` -- both satisfy this structural
 * shape). This is the parity gap vs the Streamlit precursor
 * (`frontend/components/day_plan_view.py`), which only showed two
 * `st.progress` bars (calories, protein); this renders all five reported
 * macros as mono-numeral rows.
 *
 * Provenance grammar (design system "honest kitchen ledger"): the banner is
 * solid basil when `within_tolerance` is true, dashed honey when false --
 * driven ENTIRELY by the already-computed `within_tolerance` flag, never a
 * new fit decision made here (see `app.services.day_planner`'s docstring:
 * `within_tolerance` is the SOLE fit gate, `+/-10%` kcal AND `+/-15%`
 * protein, `app.services.day_planner.MacroTolerance`).
 *
 * `total_carbs_g`/`total_fat_g`/`total_fiber_g` are always present (the
 * solver always sums whatever the recipes contain), but their matching
 * `*_relative_error` fields -- and any "target" to compare against -- are
 * only meaningful when the caller's `MacroTargets` specified that macro
 * (see `DayPlan`'s docstring: "None when the target itself didn't specify
 * that macro"). `secondaryTargets` is therefore a SEPARATE optional prop,
 * not read off the plan itself -- `DayPlan`/`PublicDayPlan` never carry a
 * `target_carbs_g`/`target_fat_g`/`target_fiber_g` field, only calories and
 * protein have a stored target. A shared-plan viewer (no original profile
 * on hand) simply omits this prop and the secondary rows show actual value
 * only, with no target/relative-error column.
 */
export interface PlanMacroSummaryPlan {
  total_calories: number;
  total_protein_g: number;
  total_carbs_g: number;
  total_fat_g: number;
  total_fiber_g: number;
  target_calories: number;
  target_protein_g: number;
  calories_relative_error: number;
  protein_relative_error: number;
  carbs_relative_error?: number | null;
  fat_relative_error?: number | null;
  fiber_relative_error?: number | null;
  within_tolerance: boolean;
}

export interface SecondaryMacroTargets {
  carbsG?: number | null;
  fatG?: number | null;
  fiberG?: number | null;
}

function MacroRow({
  label,
  actual,
  target,
  relativeError,
  unit,
}: {
  label: string;
  actual: number;
  target: number | null;
  relativeError: number | null;
  unit: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-sage-line/60 py-1.5 last:border-none">
      <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">{label}</span>
      <span className="font-mono text-sm text-cast-iron">
        {Math.round(actual)}
        {unit}
        {target != null && (
          <span className="text-cast-iron/50">
            {" "}
            / {Math.round(target)}
            {unit} target
          </span>
        )}
      </span>
      <span className="font-mono text-xs text-cast-iron/60">
        {relativeError != null ? `${Math.round(relativeError * 100)}% off target` : "no target set"}
      </span>
    </div>
  );
}

export function PlanMacroSummary({
  plan,
  secondaryTargets,
}: {
  plan: PlanMacroSummaryPlan;
  secondaryTargets?: SecondaryMacroTargets;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Macro summary</h2>

      {plan.within_tolerance ? (
        <div className="rounded-md border border-basil bg-basil/10 px-3 py-2 text-sm font-medium text-basil">
          Within tolerance
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-honey-dark bg-honey/10 px-3 py-2 text-sm font-medium text-honey-dark">
          Closest plan found — did not hit the ±10% kcal / ±15% protein tolerance band
        </div>
      )}

      <div className="flex flex-col">
        <MacroRow
          label="Calories"
          actual={plan.total_calories}
          target={plan.target_calories}
          relativeError={plan.calories_relative_error}
          unit=" kcal"
        />
        <MacroRow
          label="Protein"
          actual={plan.total_protein_g}
          target={plan.target_protein_g}
          relativeError={plan.protein_relative_error}
          unit="g"
        />
        <MacroRow
          label="Carbs"
          actual={plan.total_carbs_g}
          target={secondaryTargets?.carbsG ?? null}
          relativeError={plan.carbs_relative_error ?? null}
          unit="g"
        />
        <MacroRow
          label="Fat"
          actual={plan.total_fat_g}
          target={secondaryTargets?.fatG ?? null}
          relativeError={plan.fat_relative_error ?? null}
          unit="g"
        />
        <MacroRow
          label="Fiber"
          actual={plan.total_fiber_g}
          target={secondaryTargets?.fiberG ?? null}
          relativeError={plan.fiber_relative_error ?? null}
          unit="g"
        />
      </div>
    </section>
  );
}
