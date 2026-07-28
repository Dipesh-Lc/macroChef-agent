import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ProfileForm } from "../components/ProfileForm";
import { PantryInput, type PantryState } from "../components/PantryInput";
import { RecipeDetailModal } from "../components/RecipeDetailModal";
import { SafetyAuditPanel } from "../components/SafetyAuditPanel";
import { ShoppingList } from "../components/ShoppingList";
import { ShareButton } from "../components/ShareButton";
import { WeekCalendarGrid } from "../components/WeekCalendarGrid";
import { PantryUtilizationGauge } from "../components/PantryUtilizationGauge";
import { MacroTrendBars } from "../components/MacroTrendBars";
import { ApiError, RateLimitError } from "../api/client";
import { planWeek } from "../api/endpoints";
import type { WeeklyPlanRequest, WeeklyPlanResponse } from "../api/types";
import { DEFAULT_PROFILE_FORM_VALUE, toUserProfile } from "../lib/profile";

// Exact 422 wording from `app.api.routes_day_planner.plan_week` -- validated
// client-side too, same convention as `DayPlanPage.tsx`'s
// `MISSING_TARGETS_MESSAGE`.
const MISSING_TARGETS_MESSAGE =
  "macro_targets.calories and macro_targets.protein_g are both required to " +
  "assemble a weekly plan (the +/-10%/+/-15% tolerance gate is undefined " +
  "without them).";

// `WeeklyPlanRequest.days` bounds (app/schemas/weekly_plan.py: ge=1, le=14,
// default 7) -- not guessed.
const MIN_DAYS = 1;
const MAX_DAYS = 14;
const DEFAULT_DAYS = 7;

const MAX_PER_RECIPE_OPTIONS = [1, 2, 3, 4];

const SLOW_STATUS_AFTER_MS = 10_000;
const VERY_SLOW_STATUS_AFTER_MS = 40_000;

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
  // A multi-day solve is slower than a single day (`app.services.
  // weekly_planner.assemble_week` calls `assemble_day_plan` once per day) --
  // staged copy adapted from `HomePage.tsx`'s pattern, with a longer runway
  // before the "still working" stage since this can legitimately take
  // longer than a single day plan.
  let message = "Assembling a weekly plan…";
  if (elapsedMs >= VERY_SLOW_STATUS_AFTER_MS) {
    message = "Still working — solving each day, then building one consolidated shopping list…";
  } else if (elapsedMs >= SLOW_STATUS_AFTER_MS) {
    message = "Scoring each day's combinations against your macro targets…";
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-cast-iron/70">{message}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="h-32 animate-pulse rounded-lg border border-dashed border-sage-line bg-white"
          />
        ))}
      </div>
    </div>
  );
}

export default function WeekPlanPage() {
  const [profile, setProfile] = useState(() => toUserProfile(DEFAULT_PROFILE_FORM_VALUE));
  const [pantryState, setPantryState] = useState<PantryState>({
    typedIngredients: "",
    cuisine: null,
    mealType: "dinner",
    confirmedInventory: [],
  });
  const [days, setDays] = useState(DEFAULT_DAYS);
  const [maxPerRecipe, setMaxPerRecipe] = useState(2);
  const [rateLimitToast, setRateLimitToast] = useState<string | null>(null);
  // Lifted here (not per-`DayPlanCard`) so only one modal instance ever
  // exists for the whole week grid at a time -- see `WeekCalendarGrid`'s
  // and `DayPlanCard`'s own docstrings.
  const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null);
  // Mobile-only accordion state for the planner form + focus target for
  // "focus order after results render" -- same convention as
  // `DayPlanPage.tsx`; see that file's comments for the full rationale.
  const [formOpen, setFormOpen] = useState(false);
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);

  const planMutation = useMutation({
    mutationFn: (request: WeeklyPlanRequest) => planWeek(request),
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
    const request: WeeklyPlanRequest = {
      user_profile: profile,
      days,
      max_per_recipe: maxPerRecipe,
      inventory: pantryState.confirmedInventory,
    };
    planMutation.mutate(request);
  }

  const result: WeeklyPlanResponse | undefined = planMutation.data;
  const failure = planMutation.error;

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        {/* Mobile accordion trigger (ROADMAP Step 4.5) -- hidden at `lg:`
            and above, where the panel below is always open. */}
        <button
          type="button"
          onClick={() => setFormOpen((value) => !value)}
          aria-expanded={formOpen}
          aria-controls="week-plan-form-panel"
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
          id="week-plan-form-panel"
          className={formOpen ? "flex flex-col gap-4" : "hidden lg:flex lg:flex-col lg:gap-4"}
        >
          <ProfileForm onProfileChange={setProfile} />
          {/* Independent PantryInput instance -- pantry state is not lifted or
              shared across pages yet, same precedent as DayPlanPage/BatchPlanPage. */}
          <PantryInput onChange={setPantryState} />

          <div className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
            <h2 className="font-display text-base font-semibold text-cast-iron">Week plan options</h2>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
                Days ({MIN_DAYS}-{MAX_DAYS})
              </span>
              <input
                type="number"
                min={MIN_DAYS}
                max={MAX_DAYS}
                value={days}
                onChange={(event) =>
                  setDays(Math.min(MAX_DAYS, Math.max(MIN_DAYS, Number(event.target.value) || MIN_DAYS)))
                }
                className="rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-sm text-cast-iron focus:border-basil"
              />
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
            {planMutation.isPending ? "Building week plan…" : "Build week plan"}
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
              : "Something went wrong while building a week plan. Please try again."}
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
              Your week plan
            </h2>

            <SafetyAuditPanel rejectedRecipes={result.rejected_recipes ?? []} />

            {(result.plan.days ?? []).length === 0 ? (
              <p className="text-sm text-cast-iron/70">
                No feasible weekly plan could be assembled from your currently safe, matching recipes.
              </p>
            ) : (
              <>
                <section className="rounded-lg border border-sage-line bg-white p-4">
                  <h2 className="font-display text-base font-semibold text-cast-iron">Macro trend</h2>
                  <p className="mb-3 text-xs text-cast-iron/60">
                    Protein/carbs/fat vs. target, one bar group per day. Day totals aggregate every recipe's
                    contribution, so this view is always solid (verified) -- open a recipe's own "Where these
                    numbers come from" panel for its per-recipe grounded/estimated distinction.
                  </p>
                  <MacroTrendBars
                    days={(result.plan.days ?? []).map((day, index) => ({
                      label: `Day ${index + 1}`,
                      segments: [
                        { macro: "protein", grams: day.total_protein_g, targetGrams: day.target_protein_g, verified: true },
                        {
                          macro: "carbs",
                          grams: day.total_carbs_g,
                          targetGrams: profile.macro_targets?.carbs_g ?? null,
                          verified: true,
                        },
                        {
                          macro: "fat",
                          grams: day.total_fat_g,
                          targetGrams: profile.macro_targets?.fat_g ?? null,
                          verified: true,
                        },
                      ],
                    }))}
                  />
                </section>

                <WeekCalendarGrid
                  days={result.plan.days ?? []}
                  trustedPoolSize={result.plan.trusted_pool_size}
                  onSelectRecipe={setSelectedRecipeId}
                />

                <PantryUtilizationGauge
                  utilization={result.plan.pantry_utilization}
                  uncomparedCount={result.plan.uncompared_ingredient_count}
                />

                <ShoppingList items={result.shopping_list ?? []} />

                <div className="flex flex-wrap items-center gap-3">
                  <ShareButton planType="week" payload={result.plan} />
                </div>
              </>
            )}
          </>
        )}

        {!planMutation.isPending && !result && !failure && (
          <p className="text-sm text-cast-iron/60">
            Set your macro targets and build a full week of day plans, one consolidated shopping list, and
            a pantry-utilization estimate.
          </p>
        )}
      </div>

      {selectedRecipeId && (
        <RecipeDetailModal recipeId={selectedRecipeId} onClose={() => setSelectedRecipeId(null)} />
      )}
    </div>
  );
}
