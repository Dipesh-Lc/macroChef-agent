import { useState } from "react";
import type { IngredientContribution, Recipe } from "../api/types";
import { formatGrams, formatKcal, formatPercent } from "../lib/format";
import { macroDisplayState } from "../lib/macroDisplay";

/**
 * The transparency centerpiece: explains WHERE a recipe's macro numbers (or
 * the lack of them) came from. This panel EXPLAINS numbers, it never
 * invents them -- when nutrition is missing, ungrounded, or trust-flagged,
 * the panel still opens and shows WHY there are no numbers, rather than
 * being replaced by nothing.
 *
 * Every field rendered here comes straight from `Recipe.nutrition`
 * (`app/schemas/nutrition.py`'s `RecipeNutrition`), computed entirely by
 * `app.services.nutrition_grounding.compute_recipe_macros` at grounding
 * time -- never guessed, reworded, or decided by an LLM. See
 * `lib/macroDisplay.ts` for the trust-state chokepoint this panel reads
 * (`macroDisplayState`) but never overrides.
 */
export function NutritionBreakdown({ recipe }: { recipe: Recipe }) {
  const [expanded, setExpanded] = useState(false);
  const nutrition = recipe.nutrition;
  const state = macroDisplayState(recipe);
  const contributions: IngredientContribution[] = nutrition?.contributions ?? [];
  const ungrounded = nutrition?.ungrounded_ingredients ?? [];
  const flags = nutrition?.flags ?? [];

  return (
    <div className="rounded-md border border-dashed border-sage-line">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-cast-iron/60"
      >
        <span>Where these numbers come from</span>
        <span aria-hidden="true">{expanded ? "−" : "+"}</span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 border-t border-dashed border-sage-line px-3 py-3 text-sm">
          {!nutrition ? (
            <p className="text-cast-iron/70">
              No nutrition was computed for this recipe, so no macro numbers are shown above.
            </p>
          ) : (
            <>
              {flags.length > 0 && (
                <div className="rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-honey-dark">
                  <p className="font-medium">Trust flag: macros hidden even though grounding succeeded</p>
                  <ul className="mt-1 list-inside list-disc font-mono text-xs">
                    {flags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>
                </div>
              )}

              <CoverageBar coverage={nutrition.coverage} />

              {contributions.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="uppercase tracking-wide text-cast-iron/50">
                      <tr>
                        <th className="px-2 py-1 font-medium">Ingredient</th>
                        <th className="px-2 py-1 font-medium">Grams</th>
                        <th className="px-2 py-1 font-medium">Matched USDA food</th>
                        <th className="px-2 py-1 font-medium">kcal</th>
                        <th className="px-2 py-1 font-medium">P</th>
                        <th className="px-2 py-1 font-medium">C</th>
                        <th className="px-2 py-1 font-medium">F</th>
                        <th className="px-2 py-1 font-medium">Grounded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {contributions.map((item, index) => (
                        <tr key={`${item.name}-${index}`} className="border-t border-sage-line">
                          <td className="px-2 py-1">{item.name}</td>
                          <td className="px-2 py-1 font-mono">
                            {item.grams != null ? formatGrams(item.grams) : "—"}
                          </td>
                          <td className="px-2 py-1">
                            {item.match ? (
                              <a
                                href={`https://fdc.nal.usda.gov/food-details/${item.match.fdc_id}/nutrients`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-basil underline underline-offset-2"
                              >
                                {item.match.description}{" "}
                                <span className="text-cast-iron/50">({item.match.data_type})</span>
                              </a>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-2 py-1 font-mono">
                            {item.macros ? formatKcal(item.macros.calories) : "—"}
                          </td>
                          <td className="px-2 py-1 font-mono">
                            {item.macros ? formatGrams(item.macros.protein_g) : "—"}
                          </td>
                          <td className="px-2 py-1 font-mono">
                            {item.macros ? formatGrams(item.macros.carbs_g) : "—"}
                          </td>
                          <td className="px-2 py-1 font-mono">
                            {item.macros ? formatGrams(item.macros.fat_g) : "—"}
                          </td>
                          <td className="px-2 py-1">
                            {item.grounded ? (
                              <span className="font-mono text-basil">✓</span>
                            ) : (
                              <span className="font-mono text-cast-iron/40">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {ungrounded.length > 0 && (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
                    Not USDA-matched — excluded from totals, not guessed
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-1.5">
                    {ungrounded.map((name) => (
                      <li
                        key={name}
                        className="rounded-full border border-dashed border-sage-line px-2 py-0.5 text-xs text-cast-iron/60"
                      >
                        {name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {state === "unknown" && flags.length === 0 && (
                <p className="text-cast-iron/70">
                  This recipe's grounding did not produce a trustworthy per-serving figure (status:{" "}
                  <span className="font-mono">{nutrition.status}</span>), so no numbers are shown above.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function CoverageBar({ coverage }: { coverage: number }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs text-cast-iron/60">
        <span>USDA grounding coverage</span>
        <span className="font-mono">{formatPercent(coverage)}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-sage-line">
        <div className="h-full rounded-full bg-basil" style={{ width: `${Math.round(coverage * 100)}%` }} />
      </div>
    </div>
  );
}
