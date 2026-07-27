import type { Recipe } from "../api/types";
import { recipeArt, type RecipeArtIcon } from "../lib/placeholderImage";

/**
 * Decorative-only line icons (bowl/plate/pan) -- `aria-hidden`, no `<title>`,
 * never a substitute for real alt text. The card's real accessible label is
 * the recipe title rendered as DOM text next to this art (see `RecipeCard`),
 * never inside the art itself -- that's the fix for ROADMAP 4.4's "clipped
 * placeholder text baked into the image" complaint.
 */
function IconGlyph({ icon }: { icon: RecipeArtIcon }) {
  switch (icon) {
    case "bowl":
      return (
        <path
          d="M6 32h36a18 18 0 0 1-36 0Z M14 32c0-8 6-14 10-14s10 6 10 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      );
    case "pan":
      return (
        <path
          d="M14 30a10 10 0 1 1 20 0 10 10 0 0 1-20 0Z M44 22l8-4 M44 26l8 2"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      );
    case "plate":
    default:
      return (
        <>
          <circle cx="24" cy="24" r="16" fill="none" stroke="currentColor" strokeWidth="2.5" />
          <circle cx="24" cy="24" r="8" fill="none" stroke="currentColor" strokeWidth="2" />
        </>
      );
  }
}

/**
 * Zero-network card art: a deterministic gradient (design-token palette) +
 * a decorative food-category icon. Replaces the old `placehold.co` remote
 * image (see `lib/placeholderImage.ts`'s docstring). Since generation is
 * local/synchronous and always succeeds (title/cuisine fall back to fixed
 * strings), there is no `onError`/failure path to render around.
 */
export function RecipeArt({
  recipe,
  className = "",
}: {
  recipe: Pick<Recipe, "title" | "cuisine">;
  className?: string;
}) {
  const { gradient, icon } = recipeArt(recipe);
  const [from, to] = gradient;

  return (
    <div
      aria-hidden="true"
      className={`flex items-center justify-center rounded-md ${className}`}
      style={{ backgroundImage: `linear-gradient(135deg, ${from}, ${to})` }}
    >
      <svg viewBox="0 0 48 48" width="40" height="40" className="text-porcelain/85">
        <IconGlyph icon={icon} />
      </svg>
    </div>
  );
}
