/**
 * ROADMAP 4.4 quick fix: replaces the old `placehold.co`-backed card art
 * (a remote network call per card, with the recipe title baked into the
 * image as server-rendered text that clipped on long titles -- the "looks
 * broken" complaint) with zero-network, deterministic local art: a
 * cuisine/title-seeded gradient (design-token palette only) plus a food
 * category line-icon. The recipe title itself is never part of the
 * generated art -- it always renders as normal DOM text in `RecipeCard`,
 * so it can never be clipped or misspelled by an image-generation step.
 *
 * This module is pure data (no JSX) so it can be unit-tested for
 * determinism without a DOM; `RecipeArt.tsx` renders the SVG from it.
 */
import type { Recipe } from "../api/types";

export type RecipeArtIcon = "bowl" | "plate" | "pan";

/**
 * Gradient variants, each a pair of design tokens from `index.css`'s
 * `@theme` block (never a hardcoded hex, unlike the old placehold.co URL).
 * Order matters for `hashString` index stability -- do not reorder existing
 * entries; append new ones at the end if the palette grows.
 */
export const RECIPE_ART_GRADIENTS: readonly [string, string][] = [
  ["var(--color-basil)", "var(--color-basil-dark)"],
  ["var(--color-chili)", "var(--color-chili-dark)"],
  ["var(--color-honey)", "var(--color-honey-dark)"],
  ["var(--color-cast-iron)", "var(--color-basil-dark)"],
  ["var(--color-basil)", "var(--color-honey-dark)"],
  ["var(--color-chili-dark)", "var(--color-cast-iron)"],
];

const RECIPE_ART_ICONS: readonly RecipeArtIcon[] = ["bowl", "plate", "pan"];

/**
 * Small, dependency-free deterministic string hash (djb2 variant). Not
 * cryptographic -- only needs to be a stable function of its input so the
 * same recipe always renders the same art. `>>> 0` keeps it a non-negative
 * 32-bit integer so `% length` is always well-defined.
 */
export function hashString(value: string): number {
  let hash = 5381;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 33) ^ value.charCodeAt(index);
  }
  return hash >>> 0;
}

export interface RecipeArtSpec {
  /** CSS linear-gradient stops, e.g. `["var(--color-basil)", "var(--color-basil-dark)"]`. */
  gradient: readonly [string, string];
  icon: RecipeArtIcon;
}

/**
 * Deterministically derives card art from title+cuisine -- same recipe
 * (same title/cuisine) always produces the same gradient + icon, pinned by
 * `placeholderImage.test.ts`. Falls back to fixed strings when both fields
 * are missing/empty (never throws, never produces "undefined" seams --
 * `RecipeCard` can render this unconditionally with no failure path).
 */
export function recipeArt(recipe: Pick<Recipe, "title" | "cuisine">): RecipeArtSpec {
  const seed = `${recipe.cuisine || "meal"}|${recipe.title || "MacroChef meal"}`;
  const hash = hashString(seed);
  const gradient = RECIPE_ART_GRADIENTS[hash % RECIPE_ART_GRADIENTS.length];
  // Different modulus/prime multiplier than the gradient pick so the icon
  // doesn't just track the gradient 1:1 across the corpus.
  const icon = RECIPE_ART_ICONS[Math.floor(hash / RECIPE_ART_GRADIENTS.length) % RECIPE_ART_ICONS.length];
  return { gradient, icon };
}
