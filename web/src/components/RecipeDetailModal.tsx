import { useQuery } from "@tanstack/react-query";
import { ApiError, RateLimitError } from "../api/client";
import { getRecipe } from "../api/endpoints";
import { Modal } from "./Modal";
import { RecipeCard } from "./RecipeCard";

function friendlyErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof RateLimitError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return fallback;
}

/**
 * "Interactive Plan Recipes" roadmap item: opened when a user clicks a
 * recipe name in a day/week plan row (`PlanItem` only carries
 * `{recipe_id, title, servings}` -- see `app.schemas.day_plan.PlanItem` --
 * so the full `Recipe` has to be fetched separately via GET
 * `/recipes/{recipe_id}`). Renders the same `RecipeCard` used elsewhere,
 * without a `score`/`explanation` (there is no recommendation/scoring
 * context for a plan row), so the score-dependent sections of `RecipeCard`
 * are hidden automatically.
 */
export function RecipeDetailModal({
  recipeId,
  onClose,
}: {
  recipeId: string;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => getRecipe(recipeId),
  });

  return (
    <Modal onClose={onClose}>
      <div className="flex flex-col gap-3">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close recipe details"
            className="rounded-md border border-sage-line bg-white px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40"
          >
            Close
          </button>
        </div>

        {query.isPending && (
          <div className="rounded-lg border border-sage-line bg-white p-4">
            <p className="text-sm text-cast-iron/70">Loading recipe details…</p>
          </div>
        )}

        {query.isError && (
          <div className="rounded-lg border border-chili bg-chili/5 p-4 text-sm text-chili">
            {friendlyErrorMessage(query.error, "Could not load this recipe. Please try again.")}
          </div>
        )}

        {query.isSuccess && <RecipeCard recipe={query.data} />}
      </div>
    </Modal>
  );
}
