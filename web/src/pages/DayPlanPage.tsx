import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ProfileForm } from "../components/ProfileForm";
import { PantryInput, type PantryState } from "../components/PantryInput";
import { SafetyAuditPanel } from "../components/SafetyAuditPanel";
import { PlanMacroSummary } from "../components/PlanMacroSummary";
import { MacroRadial } from "../components/MacroRadial";
import { RecipeDetailModal } from "../components/RecipeDetailModal";
import { ShoppingList } from "../components/ShoppingList";
import { ShareButton } from "../components/ShareButton";
import { ApiError, RateLimitError } from "../api/client";
import { getShoppingList, planDay } from "../api/endpoints";
import type { DayPlanRequest, DayPlanResponse, ShoppingListResponse } from "../api/types";
import { DEFAULT_PROFILE_FORM_VALUE, toUserProfile } from "../lib/profile";

// Macro targets are now OFF by default (see `lib/profile.ts`'s
// `DEFAULT_PROFILE_FORM_VALUE`), so a value can already be present in the
// Calories/Protein inputs but simply not enabled -- tell the user to
// enable the toggle, not just "enter" a value they may have already typed.
const MISSING_TARGETS_MESSAGE =
  "Enable the Calories and Protein targets in your profile to assemble a " +
  "day plan (the +/-10%/+/-15% tolerance gate is undefined without them).";

const SLOW_STATUS_AFTER_MS = 8_000;
const VERY_SLOW_STATUS_AFTER_MS = 30_000;

function useElapsedMs(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      return;
    }
    const startedAt = Date.now();
    const interval = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => clearInterval(interval);
  }, [active]);

  return active ? elapsed : 0;
}

function LoadingStatus({ elapsedMs }: { elapsedMs: number }) {
  let message = "Assembling a day plan…";
  if (elapsedMs >= VERY_SLOW_STATUS_AFTER_MS) {
    message = "Still working — enumerating recipe combinations…";
  } else if (elapsedMs >= SLOW_STATUS_AFTER_MS) {
    message = "Scoring combinations against your macro targets…";
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-cast-iron/70">{message}</p>
      <div className="h-24 animate-pulse rounded-lg border border-dashed border-sage-line bg-white" />
    </div>
  );
}

const MAX_PER_RECIPE_OPTIONS = [1, 2, 3, 4];

// One PlanItem row: recipe title + servings. `DayPlanResponse.plan.items`
// only carries `{recipe_id, title, servings}` (see
// `app.schemas.day_plan.PlanItem`) -- no full `Recipe` (ingredients,
// nutrition, score, explanation), so `RecipeCard` can't be rendered inline
// here. Instead, the title is now a click target that opens the full
// `Recipe` (fetched via GET /recipes/{recipe_id}) in `RecipeDetailModal`,
// which itself renders `RecipeCard` with no score/explanation.
function PlanItemRow({
  recipeId,
  title,
  servings,
  onSelectRecipe,
}: {
  recipeId: string;
  title: string;
  servings: number;
  onSelectRecipe: (recipeId: string) => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-sage-line/60 py-2 last:border-none">
      <button
        type="button"
        onClick={() => onSelectRecipe(recipeId)}
        className="text-left text-sm text-cast-iron underline-offset-2 hover:underline"
      >
        {title}
      </button>
      <span className="font-mono text-sm text-cast-iron/70">
        {servings}x serving{servings === 1 ? "" : "s"}
      </span>
    </li>
  );
}

export default function DayPlanPage() {
  const [profile, setProfile] = useState(() => toUserProfile(DEFAULT_PROFILE_FORM_VALUE));
  const [pantryState, setPantryState] = useState<PantryState>({
    typedIngredients: "",
    cuisine: null,
    mealType: "dinner",
    confirmedInventory: [],
  });
  const [mealsInput, setMealsInput] = useState<string>("");
  const [maxPerRecipe, setMaxPerRecipe] = useState(2);
  const [rateLimitToast, setRateLimitToast] = useState<string | null>(null);
  const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null);
  // Mobile-only accordion state for the planner form (ROADMAP Step 4.5:
  // "planner form collapses into an accordion above results on small
  // screens"). Ignored at `lg:` and above -- the panel below forces itself
  // visible there via `lg:flex` regardless of this flag, so desktop's
  // always-open sticky sidebar is unaffected.
  const [formOpen, setFormOpen] = useState(false);
  // Focus target for "focus order after results render" (ROADMAP Step
  // 4.5's a11y pass): no prior focus management existed on this page, so a
  // screen reader user submitting the form got no cue that results
  // replaced the loading skeleton below. Mirrors `Modal.tsx`'s existing
  // `tabIndex={-1}` + `.focus()` convention for a programmatic-only focus
  // target that isn't in the natural tab order.
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);

  const planMutation = useMutation({
    mutationFn: (request: DayPlanRequest) => planDay(request),
    onError: (error) => {
      if (error instanceof RateLimitError) {
        setRateLimitToast(error.message);
      }
    },
  });

  const shoppingListMutation = useMutation({
    mutationFn: (plan: DayPlanResponse["plan"]) =>
      getShoppingList({ plan, inventory: pantryState.confirmedInventory }),
    onError: (error) => {
      if (error instanceof RateLimitError) {
        setRateLimitToast(error.message);
      }
    },
  });

  const elapsedMs = useElapsedMs(planMutation.isPending);

  useEffect(() => {
    if (!rateLimitToast) {
      return;
    }
    const timeout = setTimeout(() => setRateLimitToast(null), 6000);
    return () => clearTimeout(timeout);
  }, [rateLimitToast]);

  useEffect(() => {
    if (planMutation.isSuccess) {
      resultsHeadingRef.current?.focus();
    }
  }, [planMutation.isSuccess, planMutation.data]);

  const missingTargets =
    profile.macro_targets?.calories == null || profile.macro_targets?.protein_g == null;

  function handleBuildPlan() {
    if (missingTargets) {
      return;
    }
    const meals = mealsInput.trim() === "" ? null : Number(mealsInput);
    const request: DayPlanRequest = {
      user_profile: profile,
      meals,
      max_per_recipe: maxPerRecipe,
      inventory: pantryState.confirmedInventory,
    };
    shoppingListMutation.reset();
    planMutation.mutate(request);
  }

  const result = planMutation.data;
  const failure = planMutation.error;
  const shoppingList: ShoppingListResponse | undefined = shoppingListMutation.data;

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        {/* Mobile accordion trigger (ROADMAP Step 4.5) -- hidden at `lg:`
            and above, where the panel below is always open. */}
        <button
          type="button"
          onClick={() => setFormOpen((value) => !value)}
          aria-expanded={formOpen}
          aria-controls="day-plan-form-panel"
          className="flex items-center justify-between rounded-lg border border-sage-line bg-white px-4 py-3 text-left transition-colors duration-200 ease-out hover:bg-sage-line/20 lg:hidden"
        >
          <span className="font-display text-base font-semibold text-cast-iron">Plan details</span>
          <span
            aria-hidden="true"
            className={`text-cast-iron/60 transition-transform duration-200 ease-out ${formOpen ? "rotate-180" : ""}`}
          >
            ⌄
          </span>
        </button>

        <div
          id="day-plan-form-panel"
          className={formOpen ? "flex flex-col gap-4" : "hidden lg:flex lg:flex-col lg:gap-4"}
        >
          <ProfileForm onProfileChange={setProfile} />
          <PantryInput onChange={setPantryState} />

          <div className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
            <h2 className="font-display text-base font-semibold text-cast-iron">Day plan options</h2>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
                Meals (optional)
              </span>
              <input
                type="number"
                min={0}
                max={8}
                value={mealsInput}
                onChange={(event) => setMealsInput(event.target.value)}
                placeholder="Auto (best of 2-4 meals)"
                className="rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-sm text-cast-iron focus:border-basil"
              />
              <span className="text-xs text-cast-iron/50">
                Leave blank to let MacroChef pick the best plan across 2-4 meals.
              </span>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
                Max per recipe
              </span>
              <select
                value={maxPerRecipe}
                onChange={(event) => setMaxPerRecipe(Number(event.target.value))}
                className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
              >
                {MAX_PER_RECIPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {missingTargets && (
            <p className="rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-sm text-honey-dark">
              {MISSING_TARGETS_MESSAGE}
            </p>
          )}

          <button
            type="button"
            onClick={handleBuildPlan}
            disabled={planMutation.isPending || missingTargets}
            className="rounded-md bg-cast-iron px-4 py-2.5 text-sm font-semibold text-porcelain disabled:opacity-50"
          >
            {planMutation.isPending ? "Building day plan…" : "Build day plan"}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-4">
        {rateLimitToast && (
          <div className="rounded-md border border-honey-dark bg-honey/15 px-3 py-2 text-sm text-honey-dark">
            {rateLimitToast}
          </div>
        )}

        {failure && !(failure instanceof RateLimitError) && (
          <div className="rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
            {failure instanceof ApiError
              ? failure.message
              : "Something went wrong while building a day plan. Please try again."}
          </div>
        )}

        {planMutation.isPending && <LoadingStatus elapsedMs={elapsedMs} />}

        {!planMutation.isPending && result && (
          <>
            <h2
              ref={resultsHeadingRef}
              tabIndex={-1}
              className="font-display text-lg font-semibold text-cast-iron outline-none"
            >
              Your day plan
            </h2>

            <SafetyAuditPanel rejectedRecipes={result.rejected_recipes ?? []} />

            {(result.plan.items ?? []).length === 0 ? (
              <p className="text-sm text-cast-iron/70">
                No feasible day plan could be assembled from your currently safe, matching recipes.
              </p>
            ) : (
              <>
                <PlanMacroSummary
                  plan={result.plan}
                  secondaryTargets={{
                    carbsG: profile.macro_targets?.carbs_g ?? null,
                    fatG: profile.macro_targets?.fat_g ?? null,
                    fiberG: profile.macro_targets?.fiber_g ?? null,
                  }}
                />

                <section className="rounded-lg border border-sage-line bg-white p-4">
                  <h2 className="font-display text-base font-semibold text-cast-iron">Macros, graphically</h2>
                  <p className="mb-3 text-xs text-cast-iron/60">
                    Protein/carbs/fat vs. today's target. Day totals aggregate every recipe's contribution, so
                    this view is always solid (verified) -- open a recipe's own "Where these numbers come from"
                    panel for its per-recipe grounded/estimated distinction.
                  </p>
                  <MacroRadial
                    title="Today's macros vs target"
                    segments={[
                      {
                        macro: "protein",
                        grams: result.plan.total_protein_g,
                        targetGrams: result.plan.target_protein_g,
                        verified: true,
                      },
                      {
                        macro: "carbs",
                        grams: result.plan.total_carbs_g,
                        targetGrams: profile.macro_targets?.carbs_g ?? null,
                        verified: true,
                      },
                      {
                        macro: "fat",
                        grams: result.plan.total_fat_g,
                        targetGrams: profile.macro_targets?.fat_g ?? null,
                        verified: true,
                      },
                    ]}
                  />
                </section>

                <section className="rounded-lg border border-sage-line bg-white p-4">
                  <h2 className="font-display text-base font-semibold text-cast-iron">Meals</h2>
                  <ul className="mt-2 flex flex-col">
                    {(result.plan.items ?? []).map((item) => (
                      <PlanItemRow
                        key={item.recipe_id}
                        recipeId={item.recipe_id}
                        title={item.title}
                        servings={item.servings}
                        onSelectRecipe={setSelectedRecipeId}
                      />
                    ))}
                  </ul>
                </section>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => shoppingListMutation.mutate(result.plan)}
                    disabled={shoppingListMutation.isPending}
                    className="rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40 disabled:opacity-50"
                  >
                    {shoppingListMutation.isPending ? "Building shopping list…" : "Get shopping list"}
                  </button>

                  <ShareButton planType="day" payload={result.plan} />
                </div>

                {shoppingListMutation.error && !(shoppingListMutation.error instanceof RateLimitError) && (
                  <p className="text-sm text-chili">
                    {shoppingListMutation.error instanceof ApiError
                      ? shoppingListMutation.error.message
                      : "Could not build a shopping list. Please try again."}
                  </p>
                )}

                {shoppingList && <ShoppingList items={shoppingList.shopping_list ?? []} />}
              </>
            )}
          </>
        )}

        {!planMutation.isPending && !result && !failure && (
          <p className="text-sm text-cast-iron/60">
            Set your macro targets and build a day plan that fits within your macro tolerance.
          </p>
        )}
      </div>

      {selectedRecipeId && (
        <RecipeDetailModal recipeId={selectedRecipeId} onClose={() => setSelectedRecipeId(null)} />
      )}
    </div>
  );
}
