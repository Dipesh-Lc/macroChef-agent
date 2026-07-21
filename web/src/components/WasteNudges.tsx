import type { WasteNudge } from "../api/types";

/**
 * Trivial list render of Phase 4's expiry/waste-tracking nudges -- port of
 * `frontend/components/waste_nudge.py`'s copy/logic
 * (`app.services.waste_tracking.build_waste_nudges`). Every string here is
 * a pure template built from the structured `WasteNudge` list; no
 * LLM-authored copy anywhere.
 */
function timingPhrase(daysUntilExpiry: number | null | undefined): string {
  if (daysUntilExpiry == null || daysUntilExpiry <= 0) {
    return "today";
  }
  if (daysUntilExpiry === 1) {
    return "tomorrow";
  }
  return `in ${daysUntilExpiry} days`;
}

function waysPhrase(recipeCount: number): string {
  if (recipeCount === 0) {
    return "";
  }
  const noun = recipeCount === 1 ? "way" : "ways";
  return ` — ${recipeCount} ${noun}`;
}

export function WasteNudges({ nudges }: { nudges: WasteNudge[] | undefined }) {
  const list = nudges ?? [];
  if (list.length === 0) {
    return null;
  }

  return (
    <section className="rounded-lg border border-sage-line bg-white p-4">
      <h2 className="font-display text-base font-semibold text-cast-iron">Use it before it turns</h2>
      <div className="mt-2 flex flex-col gap-3">
        {list.map((nudge, index) => {
          const suggested = nudge.suggested_recipes ?? [];
          return (
            <div key={`${nudge.ingredient_name}-${index}`}>
              <p className="text-sm font-medium text-cast-iron">
                Use your {nudge.ingredient_name} {timingPhrase(nudge.days_until_expiry)}
                {waysPhrase(suggested.length)}
              </p>
              <ul className="mt-1 flex flex-col gap-0.5 text-sm text-cast-iron/70">
                {suggested.length === 0 ? (
                  <li>No recipe suggestions found in the corpus yet.</li>
                ) : (
                  suggested.map((recipe) => <li key={recipe.recipe_id}>{recipe.title}</li>)
                )}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
