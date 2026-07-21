/**
 * Port of `frontend/components/recommendation_cards.py`'s
 * `_batch_totals_line`: per-serving macros are already serving-invariant,
 * so this is the trivial `per_serving * target_servings` -- no new
 * nutrition computation, no USDA lookup. Reuses `macroDisplayState` (see
 * `lib/macroDisplay.ts`) so a batch total is never shown for an "unknown"
 * recipe, and is approx-prefixed ("~") for "partial" the same way
 * `macroDisplay`'s badge text already is.
 */
import type { Recipe } from "../api/types";
import { macroDisplayState } from "./macroDisplay";

export function batchTotalsLine(recipe: Recipe, targetServings: number): string | null {
  const state = macroDisplayState(recipe);
  if (state === "unknown" || !recipe.nutrition) {
    return null;
  }
  const macros = recipe.nutrition.per_serving;
  const kcal = Math.round(macros.calories * targetServings);
  const protein = Math.round(macros.protein_g * targetServings);
  const prefix = state === "partial" ? "~" : "";
  return `${targetServings} serving(s) ${prefix}≈ ${kcal} kcal · ${protein} g protein`;
}
