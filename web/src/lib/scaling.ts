/**
 * Faithful TypeScript port of `app.schemas.ingredient.scale_ingredients` /
 * `Ingredient.display()` -- SOURCE OF TRUTH is `app/schemas/ingredient.py`.
 * If the two ever disagree, the Python module wins and this file is wrong
 * (same convention `lib/macroDisplay.ts` uses for `nutrition_view.py`).
 *
 * CRITICAL semantics (do not "simplify" these away):
 * - Only ingredients with a numeric `amount` are scaled. An ingredient whose
 *   `amount` is `null`/`undefined` (e.g. "salt to taste") NEVER gets a
 *   fabricated quantity at any serving count -- it renders as the bare name
 *   forever, at any scale factor.
 * - `unit`, `name`, and `preparation` are always preserved untouched.
 * - This is pure display/shopping-list math: it never touches nutrition
 *   grounding and never recomputes `per_serving` macros (those are already
 *   serving-invariant by definition -- a caller only needs
 *   `per_serving * target_servings` for a batch total).
 */
import type { Ingredient } from "../api/types";

export function scaleIngredients(ingredients: Ingredient[], factor: number): Ingredient[] {
  return ingredients.map((ingredient) => ({
    ...ingredient,
    amount: ingredient.amount == null ? null : ingredient.amount * factor,
  }));
}

/**
 * Mirrors Python's `%g` formatting used by `Ingredient.display()`'s
 * `f"{self.amount:g}"` -- up to 6 significant digits, no trailing zeros, no
 * exponential notation for the ordinary ingredient-quantity magnitudes this
 * app deals with (falls back to a plain `String()` for anything so large or
 * small it would need exponential notation, rather than emitting one).
 */
function formatAmount(amount: number): string {
  if (Number.isInteger(amount)) {
    return String(amount);
  }
  const precise = amount.toPrecision(6);
  if (precise.includes("e") || precise.includes("E")) {
    return String(amount);
  }
  return precise.includes(".") ? precise.replace(/0+$/, "").replace(/\.$/, "") : precise;
}

/**
 * Port of `Ingredient.display()`: e.g. "150 g chicken breast", "2 tbsp
 * olive oil", or the bare "spinach"/"salt to taste" when `amount` is
 * `null` -- never a fabricated quantity.
 */
export function ingredientDisplay(ingredient: Ingredient): string {
  if (ingredient.amount == null) {
    return ingredient.name;
  }
  const amount = formatAmount(ingredient.amount);
  return ingredient.unit ? `${amount} ${ingredient.unit} ${ingredient.name}` : `${amount} ${ingredient.name}`;
}
