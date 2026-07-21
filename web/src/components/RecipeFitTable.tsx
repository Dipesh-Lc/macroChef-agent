import type { RecipeFit } from "../api/types";
import { formatPercent } from "../lib/format";

/**
 * `BatchPlan.recipe_fits` / `PublicBatchPlan.recipe_fits` table (see
 * `app.schemas.batch_plan.RecipeFit`'s docstring): per-serving macros plus
 * `kcal_relative_error`/`protein_relative_error` for each selected recipe.
 * Both relative-error fields are already non-negative fractions computed
 * server-side (`app.services.batch_planner._relative_error`, `Field(ge=0)`
 * on the schema) -- this table only formats them as percentages
 * (`formatPercent`, `lib/format.ts`), it never recomputes them.
 */
export function RecipeFitTable({ recipeFits }: { recipeFits: RecipeFit[] }) {
  if (recipeFits.length === 0) {
    return null;
  }
  return (
    <section className="rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Recipe fit</h2>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
            <tr>
              <th className="px-2 py-1.5 font-medium">Recipe</th>
              <th className="px-2 py-1.5 font-medium">kcal / serving</th>
              <th className="px-2 py-1.5 font-medium">Protein / serving</th>
              <th className="px-2 py-1.5 font-medium">kcal off target</th>
              <th className="px-2 py-1.5 font-medium">Protein off target</th>
              <th className="px-2 py-1.5 font-medium">Containers</th>
            </tr>
          </thead>
          <tbody>
            {recipeFits.map((fit) => (
              <tr key={fit.recipe_id} className="border-t border-sage-line">
                <td className="px-2 py-1.5">{fit.title}</td>
                <td className="px-2 py-1.5 font-mono">{Math.round(fit.per_serving_calories)} kcal</td>
                <td className="px-2 py-1.5 font-mono">{Math.round(fit.per_serving_protein_g)}g</td>
                <td className="px-2 py-1.5 font-mono">{formatPercent(fit.kcal_relative_error)}</td>
                <td className="px-2 py-1.5 font-mono">{formatPercent(fit.protein_relative_error)}</td>
                <td className="px-2 py-1.5 font-mono">{fit.container_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
