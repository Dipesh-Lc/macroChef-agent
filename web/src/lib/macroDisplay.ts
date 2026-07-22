/**
 * Faithful TypeScript port of `app/services/nutrition_view.py`
 * (`macro_display_state` / `trusted_per_serving`) and the badge-text logic
 * `frontend/components/recommendation_cards.py`'s `_macro_badge` derived
 * from it. SOURCE OF TRUTH is the Python module -- if the two ever
 * disagree, the Python module wins and this file is wrong.
 *
 * CRITICAL semantics (do not "simplify" these away):
 * - A non-empty `nutrition.flags` demotes the display state to "unknown"
 *   EVEN when `status` is "grounded" -- an implausible number that happens
 *   to cover every ingredient is not more trustworthy than one that
 *   doesn't (see the Python docstring for the full reasoning).
 * - "unknown" means the UI shows NO macro numbers at all, ever -- never a
 *   bare 0 or a stale/self-reported tag value.
 * - "partial" is displayed (not collapsed into "unknown") but is a
 *   systematic undercount: always rendered with an approx ("~") prefix,
 *   the grounding coverage %, and "likely undercounts" wording.
 */
import type { FoodMacros, RecipeNutrition } from "../api/types";

export type MacroDisplayState = "grounded" | "partial" | "unknown";

/**
 * Structural subset of `Recipe` (and its share-safe projection
 * `PublicRecipe`, which carries the identical `nutrition` field -- see
 * `app/schemas/share.py`'s `PublicRecipe`) that every function below
 * actually needs. Widened from a hard `Recipe` parameter so this module
 * also works for `PublicRecipe` (rendered on the public, unauthenticated
 * `SharedPlanPage`) without a type assertion -- neither function reads any
 * other `Recipe` field.
 */
export interface RecipeWithNutrition {
  nutrition?: RecipeNutrition | null;
}

export function macroDisplayState(recipe: RecipeWithNutrition): MacroDisplayState {
  if (!recipe.nutrition) {
    return "unknown";
  }
  if (recipe.nutrition.flags && recipe.nutrition.flags.length > 0) {
    return "unknown";
  }
  if (recipe.nutrition.status === "grounded") {
    return "grounded";
  }
  if (recipe.nutrition.status === "partial") {
    return "partial";
  }
  return "unknown";
}

/**
 * Mirrors `app.services.nutrition_view.trusted_per_serving`: computed
 * per-serving macros, but ONLY when fully grounded and free of any
 * trust-demoting flag. Partial, ungrounded, and flagged-grounded all
 * return `null` so a caller never mistakes an undercounted or implausible
 * total for an authoritative one.
 */
export function trustedPerServing(recipe: RecipeWithNutrition): FoodMacros | null {
  if (!recipe.nutrition || recipe.nutrition.status !== "grounded") {
    return null;
  }
  if (recipe.nutrition.flags && recipe.nutrition.flags.length > 0) {
    return null;
  }
  return recipe.nutrition.per_serving;
}

export interface MacroDisplay {
  state: MacroDisplayState;
  /** Per-serving macros -- present only when `state !== "unknown"`. */
  calories?: number;
  proteinG?: number;
  carbsG?: number;
  fatG?: number;
  /** Grounding coverage as a whole-number percent -- only set when `state === "partial"`. */
  coveragePercent?: number;
  /** N of M ingredients matched to a USDA food -- set whenever contributions were recorded. */
  matchedIngredientCount?: number;
  totalIngredientCount?: number;
  /**
   * The exact single-line badge text the Streamlit app rendered
   * (`_macro_badge`), kept for visual/copy parity: e.g.
   * "500 kcal | 40P / 50C / 15F | 6/6 ingredients USDA-matched", or
   * "~300 kcal | 20P / 30C / 8F (partial, 50% grounded, likely
   * undercounts)", or "Macros unknown".
   */
  badgeText: string;
}

export function macroDisplay(recipe: RecipeWithNutrition): MacroDisplay {
  const state = macroDisplayState(recipe);
  if (state === "unknown" || !recipe.nutrition) {
    return { state, badgeText: "Macros unknown" };
  }

  const macros = recipe.nutrition.per_serving;
  let badgeText = `${Math.round(macros.calories)} kcal | ${Math.round(macros.protein_g)}P / ${Math.round(macros.carbs_g)}C / ${Math.round(macros.fat_g)}F`;

  let coveragePercent: number | undefined;
  if (state === "partial") {
    coveragePercent = Math.round(recipe.nutrition.coverage * 100);
    badgeText = `~${badgeText} (partial, ${coveragePercent}% grounded, likely undercounts)`;
  }

  const contributions = recipe.nutrition.contributions ?? [];
  let matchedIngredientCount: number | undefined;
  let totalIngredientCount: number | undefined;
  if (contributions.length > 0) {
    matchedIngredientCount = contributions.filter((item) => item.grounded).length;
    totalIngredientCount = contributions.length;
    badgeText = `${badgeText} | ${matchedIngredientCount}/${totalIngredientCount} ingredients USDA-matched`;
  }

  return {
    state,
    calories: macros.calories,
    proteinG: macros.protein_g,
    carbsG: macros.carbs_g,
    fatG: macros.fat_g,
    coveragePercent,
    matchedIngredientCount,
    totalIngredientCount,
    badgeText,
  };
}
