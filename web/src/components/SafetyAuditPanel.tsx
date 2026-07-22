import { useState } from "react";
import type { RejectedRecipe } from "../api/types";

/**
 * Ledger-stamp styling for the deterministic safety filter's output.
 * Always rendered when a response exists -- including the zero case -- so
 * "nothing was rejected" is stated as plainly as "N were rejected", never
 * silently omitted. Every recipe/reason shown here came straight from
 * `RecommendationResponse.rejected_recipes`, itself produced entirely by
 * `app.services.constraint_engine` (see CLAUDE.md: the LLM never decides an
 * allergy/diet outcome) -- this component only renders that decision.
 */
export function SafetyAuditPanel({ rejectedRecipes }: { rejectedRecipes: RejectedRecipe[] }) {
  const [expanded, setExpanded] = useState(false);
  const count = rejectedRecipes.length;

  return (
    <section className="rounded-lg border-2 border-chili/70 bg-white">
      <div className="flex items-center justify-between gap-3 border-b border-dashed border-chili/40 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold uppercase tracking-widest text-chili">
            Safety audit
          </span>
          <span className="font-mono text-sm text-cast-iron">
            {count} recipe{count === 1 ? "" : "s"} rejected by the deterministic safety filter
          </span>
        </div>
        {count > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="shrink-0 text-xs font-medium text-chili underline underline-offset-2"
          >
            {expanded ? "Hide reasons" : "Show reasons"}
          </button>
        )}
      </div>

      {expanded && count > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-cast-iron/50">
            <tr>
              <th className="px-4 py-2 font-medium">Recipe</th>
              <th className="px-4 py-2 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {rejectedRecipes.map((rejected) => (
              <tr key={rejected.recipe_id} className="border-t border-sage-line">
                <td className="px-4 py-2">{rejected.title}</td>
                <td className="px-4 py-2 text-cast-iron/80">{rejected.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
