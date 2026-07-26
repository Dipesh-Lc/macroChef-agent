import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { RecipeSearchForm } from "../components/RecipeSearchForm";
import { RecipeDetailModal } from "../components/RecipeDetailModal";
import { ShoppingList } from "../components/ShoppingList";
import { ApiError, RateLimitError } from "../api/client";
import { getShoppingListForItems, searchRecipes } from "../api/endpoints";
import type { PlanItem, Recipe, RecipeSearchRequest, RecipeSearchResponse } from "../api/types";
import { macroDisplay } from "../lib/macroDisplay";

/**
 * Objective 3 (frontend half): search the recipe corpus with filters, add
 * results to a customizable, client-side-only plan (a flat `list[PlanItem]`
 * -- NOT a full solver-generated `DayPlan`/`WeeklyPlan`; see the task spec's
 * design decision 1 for why this deliberately has no macro targets/day-by-
 * day scheduling), then generate a shopping list from that plan and/or open
 * any recipe's full details.
 *
 * SAFETY: this page makes no allergy/diet decision of its own. Every result
 * from `searchRecipes` already had allergen/diet exclusion applied
 * server-side (`app.api.routes_recommendations.search_recipes`, via
 * `app.services.constraint_engine.contains_allergen`/`violates_diet_type`)
 * -- adding/removing a recipe here, or generating its shopping list, is pure
 * client-side bookkeeping and quantity arithmetic (`getShoppingListForItems`
 * -> `app.services.procurement_service.build_shopping_list_for_items`),
 * never a re-filter and never a nutrition computation of its own.
 */

function friendlyErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof RateLimitError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return fallback;
}

function ResultRow({
  recipe,
  inPlan,
  onAdd,
  onViewDetails,
}: {
  recipe: Recipe;
  inPlan: boolean;
  onAdd: (recipe: Recipe) => void;
  onViewDetails: (recipeId: string) => void;
}) {
  const macros = macroDisplay(recipe);
  const metaParts = [recipe.cuisine ?? "Any cuisine", recipe.meal_type ?? "meal"];

  return (
    <li className="flex flex-col gap-2 border-b border-sage-line/60 py-3 last:border-none sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-0.5">
        <span className="font-display text-sm font-semibold text-cast-iron">{recipe.title}</span>
        <span className="text-xs text-cast-iron/60">{metaParts.join(" · ")}</span>
        <span className="font-mono text-xs text-cast-iron/70">{macros.badgeText}</span>
      </div>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={() => onViewDetails(recipe.recipe_id)}
          className="rounded-md border border-sage-line px-3 py-1.5 text-xs font-medium text-cast-iron hover:bg-sage-line/40"
        >
          View details
        </button>
        <button
          type="button"
          onClick={() => onAdd(recipe)}
          disabled={inPlan}
          className="rounded-md border border-basil px-3 py-1.5 text-xs font-medium text-basil disabled:opacity-50"
        >
          {inPlan ? "In plan" : "Add to plan"}
        </button>
      </div>
    </li>
  );
}

function PlanItemRow({
  item,
  onServingsChange,
  onRemove,
  onViewDetails,
}: {
  item: PlanItem;
  onServingsChange: (recipeId: string, servings: number) => void;
  onRemove: (recipeId: string) => void;
  onViewDetails: (recipeId: string) => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-sage-line/60 py-2 last:border-none">
      <button
        type="button"
        onClick={() => onViewDetails(item.recipe_id)}
        className="text-left text-sm text-cast-iron underline-offset-2 hover:underline"
      >
        {item.title}
      </button>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5">
          <span className="sr-only">{`${item.title} servings`}</span>
          <input
            type="number"
            min={1}
            value={item.servings}
            onChange={(event) => {
              const next = Number(event.target.value);
              onServingsChange(item.recipe_id, Number.isFinite(next) && next >= 1 ? next : 1);
            }}
            className="w-16 rounded-md border border-sage-line bg-white px-2 py-1 font-mono text-sm text-cast-iron focus:border-basil"
          />
        </label>
        <button
          type="button"
          onClick={() => onRemove(item.recipe_id)}
          aria-label={`Remove ${item.title} from plan`}
          className="rounded-md border border-sage-line px-2 py-1 text-xs font-medium text-cast-iron hover:bg-sage-line/40"
        >
          Remove
        </button>
      </div>
    </li>
  );
}

export default function RecipeSearchPage() {
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null);

  const searchMutation = useMutation({
    mutationFn: (request: RecipeSearchRequest) => searchRecipes(request),
  });

  const shoppingListMutation = useMutation({
    mutationFn: () => getShoppingListForItems({ items: planItems, inventory: [] }),
  });

  const result: RecipeSearchResponse | undefined = searchMutation.data;
  const searchFailure = searchMutation.error;

  function handleAdd(recipe: Recipe) {
    setPlanItems((current) => {
      if (current.some((item) => item.recipe_id === recipe.recipe_id)) {
        return current;
      }
      return [...current, { recipe_id: recipe.recipe_id, title: recipe.title, servings: 1 }];
    });
  }

  function handleRemove(recipeId: string) {
    setPlanItems((current) => current.filter((item) => item.recipe_id !== recipeId));
  }

  function handleServingsChange(recipeId: string, servings: number) {
    setPlanItems((current) =>
      current.map((item) => (item.recipe_id === recipeId ? { ...item, servings } : item)),
    );
  }

  function handleGenerateShoppingList() {
    shoppingListMutation.mutate();
  }

  const planRecipeIds = new Set(planItems.map((item) => item.recipe_id));

  return (
    <div className="flex flex-col gap-6">
      <RecipeSearchForm
        onSearch={(request) => searchMutation.mutate(request)}
        isPending={searchMutation.isPending}
      />

      {searchFailure && (
        <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {friendlyErrorMessage(searchFailure, "Something went wrong while searching. Please try again.")}
        </div>
      )}

      {result && (
        <section className="rounded-lg border border-sage-line bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-display text-base font-semibold text-cast-iron">
              Results ({result.total_matched})
            </h2>
          </div>

          {result.macro_unavailable_excluded > 0 && (
            <p className="mt-1 rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-xs text-honey-dark">
              {result.macro_unavailable_excluded} recipe
              {result.macro_unavailable_excluded === 1 ? "" : "s"} excluded from macro-filtered
              results due to incomplete nutrition data.
            </p>
          )}

          {(result.results ?? []).length === 0 ? (
            <p className="mt-2 text-sm text-cast-iron/70">No recipes matched these filters.</p>
          ) : (
            <ul className="mt-2 flex flex-col">
              {(result.results ?? []).map((recipe) => (
                <ResultRow
                  key={recipe.recipe_id}
                  recipe={recipe}
                  inPlan={planRecipeIds.has(recipe.recipe_id)}
                  onAdd={handleAdd}
                  onViewDetails={setSelectedRecipeId}
                />
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="rounded-lg border border-sage-line bg-white p-4">
        <h2 className="font-display text-base font-semibold text-cast-iron">Your plan</h2>

        {planItems.length === 0 ? (
          <p className="mt-2 text-sm text-cast-iron/70">
            Add recipes from your search results to build a plan.
          </p>
        ) : (
          <>
            <ul className="mt-2 flex flex-col">
              {planItems.map((item) => (
                <PlanItemRow
                  key={item.recipe_id}
                  item={item}
                  onServingsChange={handleServingsChange}
                  onRemove={handleRemove}
                  onViewDetails={setSelectedRecipeId}
                />
              ))}
            </ul>

            <button
              type="button"
              onClick={handleGenerateShoppingList}
              disabled={shoppingListMutation.isPending}
              className="mt-3 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40 disabled:opacity-50"
            >
              {shoppingListMutation.isPending ? "Building shopping list…" : "Generate shopping list"}
            </button>

            {shoppingListMutation.error && (
              <p className="mt-2 text-sm text-chili">
                {friendlyErrorMessage(
                  shoppingListMutation.error,
                  "Could not build a shopping list. Please try again.",
                )}
              </p>
            )}

            {shoppingListMutation.data && (
              <div className="mt-3">
                <ShoppingList items={shoppingListMutation.data.shopping_list ?? []} />
              </div>
            )}
          </>
        )}
      </section>

      {selectedRecipeId && (
        <RecipeDetailModal recipeId={selectedRecipeId} onClose={() => setSelectedRecipeId(null)} />
      )}
    </div>
  );
}
