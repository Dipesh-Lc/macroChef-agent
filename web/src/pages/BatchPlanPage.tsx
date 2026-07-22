import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ProfileForm } from "../components/ProfileForm";
import { PantryInput, type PantryState } from "../components/PantryInput";
import { SafetyAuditPanel } from "../components/SafetyAuditPanel";
import { ShoppingList } from "../components/ShoppingList";
import { ShareButton } from "../components/ShareButton";
import { BatchContainerGrid } from "../components/BatchContainerGrid";
import { RecipeFitTable } from "../components/RecipeFitTable";
import { ApiError, RateLimitError } from "../api/client";
import { planBatch } from "../api/endpoints";
import type { BatchPlanRequest, BatchPlanResponse } from "../api/types";
import { DEFAULT_PROFILE_FORM_VALUE, toUserProfile } from "../lib/profile";

// Wording mirrors the ACTUAL FastAPI/Pydantic 422 shape observed for
// `BatchPlanRequest.per_container_target_calories`/
// `per_container_target_protein_g` (both `Field(gt=0)`, required --
// `app/schemas/batch_plan.py`): `plan_batch` raises no custom
// `HTTPException` for this case, unlike `plan_day`/`plan_week` -- Pydantic's
// own validation rejects the request first, with one `{loc, msg}` entry per
// field: `"Input should be greater than 0"` for a non-positive value,
// `"Field required"` for a missing one (verified via a live curl against
// POST /plan/batch during W4 acceptance testing). This mirrors that
// per-field shape instead of a single paraphrased sentence.
function targetValidationMessages(perContainerCalories: number, perContainerProteinG: number): string[] {
  const messages: string[] = [];
  if (!(perContainerCalories > 0)) {
    messages.push("per_container_target_calories: Input should be greater than 0");
  }
  if (!(perContainerProteinG > 0)) {
    messages.push("per_container_target_protein_g: Input should be greater than 0");
  }
  return messages;
}

// `BatchPlanRequest` bounds (app/schemas/batch_plan.py) -- not guessed.
const MIN_CONTAINERS = 1;
const MAX_CONTAINERS = 30;
const DEFAULT_CONTAINERS = 10;
const MIN_RECIPES_BOUND = 1;
const MAX_RECIPES_BOUND = 5;
const DEFAULT_MIN_RECIPES = 2;
const DEFAULT_MAX_RECIPES = 3;

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
  let message = "Assembling a meal-prep batch plan…";
  if (elapsedMs >= VERY_SLOW_STATUS_AFTER_MS) {
    message = "Still working — filtering and sorting eligible recipes…";
  } else if (elapsedMs >= SLOW_STATUS_AFTER_MS) {
    message = "Scoring recipes against your per-container target…";
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-cast-iron/70">{message}</p>
      <div className="h-24 animate-pulse rounded-lg border border-dashed border-sage-line bg-white" />
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-sm text-cast-iron focus:border-basil"
      />
    </label>
  );
}

export default function BatchPlanPage() {
  const [profile, setProfile] = useState(() => toUserProfile(DEFAULT_PROFILE_FORM_VALUE));
  const [pantryState, setPantryState] = useState<PantryState>({
    typedIngredients: "",
    cuisine: null,
    mealType: "dinner",
    confirmedInventory: [],
  });
  const [perContainerCalories, setPerContainerCalories] = useState(500);
  const [perContainerProteinG, setPerContainerProteinG] = useState(35);
  const [containers, setContainers] = useState(DEFAULT_CONTAINERS);
  const [minRecipes, setMinRecipes] = useState(DEFAULT_MIN_RECIPES);
  const [maxRecipes, setMaxRecipes] = useState(DEFAULT_MAX_RECIPES);
  const [rateLimitToast, setRateLimitToast] = useState<string | null>(null);

  const planMutation = useMutation({
    mutationFn: (request: BatchPlanRequest) => planBatch(request),
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

  const targetMessages = targetValidationMessages(perContainerCalories, perContainerProteinG);
  const minMaxInvalid = minRecipes > maxRecipes;
  const targetsInvalid = targetMessages.length > 0 || minMaxInvalid;

  function handleBuildPlan() {
    if (targetsInvalid) {
      return;
    }
    const request: BatchPlanRequest = {
      user_profile: profile,
      per_container_target_calories: perContainerCalories,
      per_container_target_protein_g: perContainerProteinG,
      containers,
      min_recipes: minRecipes,
      max_recipes: maxRecipes,
      inventory: pantryState.confirmedInventory,
    };
    planMutation.mutate(request);
  }

  const result: BatchPlanResponse | undefined = planMutation.data;
  const failure = planMutation.error;

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        <ProfileForm onProfileChange={setProfile} />
        {/* Independent PantryInput instance -- pantry state is not lifted or
            shared across pages yet, same precedent as DayPlanPage/WeekPlanPage. */}
        <PantryInput onChange={setPantryState} />

        <div className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
          <h2 className="font-display text-base font-semibold text-cast-iron">Batch plan options</h2>

          <div className="grid grid-cols-2 gap-2">
            <NumberField
              label="Calories / container"
              value={perContainerCalories}
              onChange={setPerContainerCalories}
              min={1}
            />
            <NumberField
              label="Protein (g) / container"
              value={perContainerProteinG}
              onChange={setPerContainerProteinG}
              min={1}
            />
          </div>

          <NumberField
            label={`Containers (${MIN_CONTAINERS}-${MAX_CONTAINERS})`}
            value={containers}
            onChange={(v) => setContainers(Math.min(MAX_CONTAINERS, Math.max(MIN_CONTAINERS, v || MIN_CONTAINERS)))}
            min={MIN_CONTAINERS}
            max={MAX_CONTAINERS}
          />

          <div className="grid grid-cols-2 gap-2">
            <NumberField
              label={`Min recipes (${MIN_RECIPES_BOUND}-${MAX_RECIPES_BOUND})`}
              value={minRecipes}
              onChange={(v) =>
                setMinRecipes(Math.min(MAX_RECIPES_BOUND, Math.max(MIN_RECIPES_BOUND, v || MIN_RECIPES_BOUND)))
              }
              min={MIN_RECIPES_BOUND}
              max={MAX_RECIPES_BOUND}
            />
            <NumberField
              label={`Max recipes (${MIN_RECIPES_BOUND}-${MAX_RECIPES_BOUND})`}
              value={maxRecipes}
              onChange={(v) =>
                setMaxRecipes(Math.min(MAX_RECIPES_BOUND, Math.max(MIN_RECIPES_BOUND, v || MIN_RECIPES_BOUND)))
              }
              min={MIN_RECIPES_BOUND}
              max={MAX_RECIPES_BOUND}
            />
          </div>
        </div>

        {targetsInvalid && (
          <div className="rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-sm text-honey-dark">
            {targetMessages.length > 0 ? (
              <ul className="list-inside list-disc">
                {targetMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            ) : (
              <p>min_recipes must be less than or equal to max_recipes.</p>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={handleBuildPlan}
          disabled={planMutation.isPending || targetsInvalid}
          className="rounded-md bg-cast-iron px-4 py-2.5 text-sm font-semibold text-porcelain disabled:opacity-50"
        >
          {planMutation.isPending ? "Building meal-prep plan…" : "Build meal-prep plan"}
        </button>
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
              : "Something went wrong while building a meal-prep plan. Please try again."}
          </div>
        )}

        {planMutation.isPending && <LoadingStatus elapsedMs={elapsedMs} />}

        {!planMutation.isPending && result && (
          <>
            <SafetyAuditPanel rejectedRecipes={result.rejected_recipes ?? []} />

            {!result.plan.within_tolerance && (
              <div className="rounded-md border border-dashed border-honey-dark bg-honey/10 px-3 py-2 text-sm font-medium text-honey-dark">
                Closest available — no recipe fit the per-container target band
              </div>
            )}

            {result.plan.recipes_selected < minRecipes && (
              <div className="rounded-md border border-dashed border-honey-dark bg-honey/10 px-3 py-2 text-sm font-medium text-honey-dark">
                Variety target not met (only {result.plan.recipes_selected} of {minRecipes} requested)
              </div>
            )}

            <BatchContainerGrid items={result.plan.items ?? []} containers={result.plan.containers} />

            <RecipeFitTable recipeFits={result.plan.recipe_fits ?? []} />

            <ShoppingList items={result.shopping_list ?? []} />

            <div className="flex flex-wrap items-center gap-3">
              <ShareButton planType="batch" payload={result.plan} />
            </div>
          </>
        )}

        {!planMutation.isPending && !result && !failure && (
          <p className="text-sm text-cast-iron/60">
            Set a per-container calorie/protein target and build a meal-prep batch plan sized to whole
            containers, with one consolidated shopping list.
          </p>
        )}
      </div>
    </div>
  );
}
