import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ProfileForm } from "../components/ProfileForm";
import { PantryInput, type PantryState } from "../components/PantryInput";
import { SafetyAuditPanel } from "../components/SafetyAuditPanel";
import { RecipeCard } from "../components/RecipeCard";
import { ShoppingList } from "../components/ShoppingList";
import { TasteProfilePanel } from "../components/TasteProfilePanel";
import { WasteNudges } from "../components/WasteNudges";
import { DebugDrawer } from "../components/DebugDrawer";
import { ApiError, RateLimitError } from "../api/client";
import { recommendRecipes } from "../api/endpoints";
import type { RecommendationRequest, UserProfile } from "../api/types";
import { DEFAULT_PROFILE_FORM_VALUE, toUserProfile } from "../lib/profile";

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

  // Ignore any stale reading from a previous run rather than resetting
  // state synchronously inside the effect above -- the component only
  // ever reads this value while `active` is true.
  return active ? elapsed : 0;
}

function LoadingStatus({ elapsedMs }: { elapsedMs: number }) {
  let message = "Finding recipes…";
  if (elapsedMs >= VERY_SLOW_STATUS_AFTER_MS) {
    message = "Still working — the solver is thorough…";
  } else if (elapsedMs >= SLOW_STATUS_AFTER_MS) {
    message = "Scoring recipes against your pantry…";
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-cast-iron/70">{message}</p>
      <div className="flex flex-col gap-3">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="h-28 animate-pulse rounded-lg border border-dashed border-sage-line bg-white"
          />
        ))}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [profile, setProfile] = useState<UserProfile>(() => toUserProfile(DEFAULT_PROFILE_FORM_VALUE));
  const [pantryState, setPantryState] = useState<PantryState>({
    typedIngredients: "",
    cuisine: null,
    mealType: "dinner",
    confirmedInventory: [],
  });
  const [rateLimitToast, setRateLimitToast] = useState<string | null>(null);

  const recommendMutation = useMutation({
    mutationFn: (request: RecommendationRequest) => recommendRecipes(request),
    onError: (error) => {
      if (error instanceof RateLimitError) {
        setRateLimitToast(error.message);
      }
    },
  });

  const elapsedMs = useElapsedMs(recommendMutation.isPending);

  useEffect(() => {
    if (!rateLimitToast) {
      return;
    }
    const timeout = setTimeout(() => setRateLimitToast(null), 6000);
    return () => clearTimeout(timeout);
  }, [rateLimitToast]);

  function handleFindRecipes() {
    const request: RecommendationRequest = {
      input_type: "text",
      typed_ingredients: pantryState.typedIngredients || null,
      confirmed_inventory:
        pantryState.confirmedInventory.length > 0 ? pantryState.confirmedInventory : null,
      user_profile: profile,
      cuisine_preference: pantryState.cuisine,
      meal_type: pantryState.mealType,
    };
    recommendMutation.mutate(request);
  }

  const result = recommendMutation.data;
  const failure = recommendMutation.error;

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        <ProfileForm onProfileChange={setProfile} />
        <PantryInput onChange={setPantryState} />
        <button
          type="button"
          onClick={handleFindRecipes}
          disabled={recommendMutation.isPending}
          className="rounded-md bg-cast-iron px-4 py-2.5 text-sm font-semibold text-porcelain disabled:opacity-50"
        >
          {recommendMutation.isPending ? "Finding recipes…" : "Find recipes"}
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
              : "Something went wrong while finding recipes. Please try again."}
          </div>
        )}

        {recommendMutation.isPending && <LoadingStatus elapsedMs={elapsedMs} />}

        {!recommendMutation.isPending && result && (
          <>
            {result.errors && result.errors.length > 0 && (
              <div className="rounded-md border border-honey-dark bg-honey/10 px-3 py-2 text-sm text-honey-dark">
                <ul className="list-inside list-disc">
                  {result.errors.map((message, index) => (
                    <li key={index}>{message}</li>
                  ))}
                </ul>
              </div>
            )}

            <SafetyAuditPanel rejectedRecipes={result.rejected_recipes ?? []} />

            {(result.recommendations ?? []).length === 0 ? (
              <p className="text-sm text-cast-iron/70">
                No recipes matched your pantry and profile. Try loosening a constraint or adding more
                ingredients.
              </p>
            ) : (
              <div className="flex flex-col gap-4">
                {(result.recommendations ?? []).map((recommendation) => (
                  <RecipeCard key={recommendation.recipe.recipe_id} recommendation={recommendation} />
                ))}
              </div>
            )}

            <ShoppingList items={result.shopping_list ?? []} />
            <TasteProfilePanel tasteProfile={result.taste_profile} />
            <WasteNudges nudges={result.waste_nudges} />
          </>
        )}

        {!recommendMutation.isPending && !result && !failure && (
          <p className="text-sm text-cast-iron/60">
            Add what's in your kitchen and set your profile, then find recipes.
          </p>
        )}

        <DebugDrawer response={result ?? null} />
      </div>
    </div>
  );
}
