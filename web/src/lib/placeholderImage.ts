/**
 * Port of `frontend/components/recommendation_cards.py`'s
 * `_recipe_image_url` -- same placehold.co pattern, same colors, same
 * literal "%0A" line break between cuisine and title (not a real newline
 * character; the Python f-string embeds the already-percent-encoded
 * sequence directly, so this does too).
 */
import type { Recipe } from "../api/types";

/** Mirrors Python's `urllib.parse.quote_plus` (spaces -> "+", not "%20"). */
function quotePlus(value: string): string {
  return encodeURIComponent(value).replace(/%20/g, "+");
}

export function recipeImageUrl(recipe: Pick<Recipe, "title" | "cuisine">): string {
  const title = quotePlus(recipe.title || "MacroChef meal");
  const cuisine = quotePlus(recipe.cuisine || "meal");
  return `https://placehold.co/520x360/243f36/bff4de/png?text=${cuisine}+recipe%0A${title}`;
}
