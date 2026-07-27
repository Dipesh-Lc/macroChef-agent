import { useState } from "react";
import type { Recipe } from "../api/types";
import { RecipeArt } from "./RecipeArt";

/**
 * Port of `frontend/components/saved_recipe_library.py`'s
 * `render_saved_recipe_library`: the persistent "My recipe library" list.
 *
 * A saved-library `Recipe` carries no `RecipeScore`/explanation (those only
 * exist on a `MealRecommendation` from `/recipes/recommend`), so this is a
 * lighter row, not `RecipeCard` -- forcing `RecipeCard`'s shape here would
 * mean fabricating a fake score, which nothing in this app should ever do.
 */
function SavedRecipeRow({
  recipe,
  onDelete,
  isDeleting,
}: {
  recipe: Recipe;
  onDelete: (recipeId: string) => void;
  isDeleting: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  // Real image takes priority; falls back to zero-network local art if
  // absent or if the real one fails to load (see `RecipeCandidateCards`'s
  // matching comment).
  const realImageUrl = recipe.image_url ?? recipe.image_path;
  const metaParts = [
    recipe.cuisine ?? "Any cuisine",
    recipe.meal_type ?? "meal",
    recipe.cook_time_min ? `${recipe.cook_time_min} min` : "time unknown",
  ];

  return (
    <article className="overflow-hidden rounded-lg border border-sage-line bg-white shadow-sm">
      <div className="grid grid-cols-[96px_1fr_auto] items-center gap-3 p-3">
        {realImageUrl && !imageFailed ? (
          <img
            src={realImageUrl}
            alt={recipe.title}
            onError={() => setImageFailed(true)}
            className="h-16 w-full rounded-md object-cover"
          />
        ) : (
          <RecipeArt recipe={recipe} className="h-16 w-full" />
        )}

        <div className="flex flex-col gap-0.5">
          <h3 className="font-display text-sm font-semibold text-cast-iron">{recipe.title}</h3>
          <p className="text-xs text-cast-iron/60">{metaParts.join(" · ")}</p>
          {recipe.description && (
            <p className="text-sm text-cast-iron/80">{recipe.description}</p>
          )}
        </div>

        <button
          type="button"
          onClick={() => onDelete(recipe.recipe_id)}
          disabled={isDeleting}
          className="shrink-0 rounded-md border border-chili/60 px-3 py-1.5 text-xs font-medium text-chili disabled:opacity-50"
        >
          {isDeleting ? "Deleting…" : "Delete"}
        </button>
      </div>
    </article>
  );
}

export function SavedRecipeLibrary({
  recipes,
  isLoading,
  loadError,
  onRefresh,
  onDelete,
  deletingRecipeId,
  deleteError,
}: {
  recipes: Recipe[];
  isLoading: boolean;
  loadError: string | null;
  onRefresh: () => void;
  onDelete: (recipeId: string) => void;
  deletingRecipeId: string | null;
  deleteError: string | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-base font-semibold text-cast-iron">My recipe library</h2>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40 disabled:opacity-50"
        >
          {isLoading ? "Refreshing…" : "Refresh saved recipes"}
        </button>
      </div>

      {loadError && (
        <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {loadError}
        </div>
      )}

      {deleteError && (
        <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {deleteError}
        </div>
      )}

      {!loadError && !isLoading && recipes.length === 0 && (
        <p className="text-sm text-cast-iron/60">
          No saved recipes yet. Discover recipes above, or come back after your first plan.
        </p>
      )}

      {recipes.length > 0 && (
        <div className="flex flex-col gap-3">
          {recipes.map((recipe) => (
            <SavedRecipeRow
              key={recipe.recipe_id}
              recipe={recipe}
              onDelete={onDelete}
              isDeleting={deletingRecipeId === recipe.recipe_id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
