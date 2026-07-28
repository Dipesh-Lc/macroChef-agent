import { useCallback, useEffect, useRef, useState } from "react";
import { ProfileForm } from "../components/ProfileForm";
import { PantryInput, type PantryState } from "../components/PantryInput";
import { SafetyAuditPanel } from "../components/SafetyAuditPanel";
import { RecipeCard } from "../components/RecipeCard";
import { RunProgressTimeline } from "../components/RunProgressTimeline";
import { ShoppingList } from "../components/ShoppingList";
import { TasteProfilePanel } from "../components/TasteProfilePanel";
import { WasteNudges } from "../components/WasteNudges";
import { DebugDrawer } from "../components/DebugDrawer";
import { ApiError, RateLimitError } from "../api/client";
import { recommendRecipes } from "../api/endpoints";
import { streamRecommend, type NodeRunEvent } from "../lib/sse";
import type { RecommendationRequest, RecommendationResponse, UserProfile } from "../api/types";
import { DEFAULT_PROFILE_FORM_VALUE, toUserProfile } from "../lib/profile";

const INITIAL_VISIBLE_COUNT = 5;
const VISIBLE_COUNT_STEP = 5;

type StreamPhase = "idle" | "streaming" | "error";

/**
 * Drives `POST /recipes/recommend/stream` (ROADMAP.md Step 4.2) and exposes
 * the live node events + terminal result/error as plain state, so `HomePage`
 * can render `RunProgressTimeline` while `phase === "streaming"/"error"` and
 * swap in the existing results view once `result` lands -- see
 * `RunProgressTimeline`'s docstring for why that swap happens here, in
 * `HomePage`, rather than inside the timeline component itself.
 *
 * Sync-endpoint fallback: the streaming endpoint is additive (Step 3.1's
 * docstring) and shares the sync endpoint's auth/rate-limit/graph logic
 * byte-for-byte, but SOME environment between this browser and the backend
 * (a corporate proxy that buffers `text/event-stream`, a browser without a
 * readable-stream response body, ...) could still break the stream
 * transport itself before any node event ever arrives. In exactly that
 * case -- an error surfaces with zero events received -- this falls back to
 * the plain `POST /recipes/recommend` call (`recommendRecipes`) the app
 * used before this step, so a transport-level SSE hiccup doesn't turn into
 * "the planner stopped working". Once at least one live event has rendered,
 * a later failure is shown as a normal error+retry instead: silently
 * discarding real, already-displayed progress and re-running synchronously
 * would be a more confusing UX than just asking the user to retry.
 */
function useRecommendStream() {
  const [events, setEvents] = useState<NodeRunEvent[]>([]);
  const [phase, setPhase] = useState<StreamPhase>("idle");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [rateLimitMessage, setRateLimitMessage] = useState<string | null>(null);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const lastRequestRef = useRef<RecommendationRequest | null>(null);

  const run = useCallback(async (request: RecommendationRequest) => {
    lastRequestRef.current = request;
    setEvents([]);
    setErrorDetail(null);
    setRateLimitMessage(null);
    setResult(null);
    setPhase("streaming");

    let receivedAnyEvent = false;
    try {
      for await (const event of streamRecommend(request)) {
        if (event.type === "node") {
          receivedAnyEvent = true;
          setEvents((current) => [...current, event.data]);
        } else if (event.type === "result") {
          setResult(event.data);
          setPhase("idle");
        } else if (event.type === "error") {
          setErrorDetail(event.data.detail);
          setPhase("error");
        }
      }
    } catch (caught) {
      if (caught instanceof RateLimitError) {
        // Matches this app's existing rate-limit UX (a transient toast, no
        // persistent error panel/retry button) -- never attempt the sync
        // fallback here, that would just trip the same shared limit again.
        setRateLimitMessage(caught.message);
        setPhase("idle");
        return;
      }

      if (!receivedAnyEvent) {
        // No live progress was ever shown -- safe to fall back to the
        // synchronous endpoint transparently (see this hook's docstring).
        try {
          const response = await recommendRecipes(request);
          setResult(response);
          setPhase("idle");
          return;
        } catch (fallbackError) {
          if (fallbackError instanceof RateLimitError) {
            setRateLimitMessage(fallbackError.message);
            setPhase("idle");
            return;
          }
          setErrorDetail(
            fallbackError instanceof ApiError
              ? fallbackError.message
              : "Something went wrong while finding recipes. Please try again.",
          );
          setPhase("error");
          return;
        }
      }

      setErrorDetail(
        caught instanceof ApiError
          ? caught.message
          : "Something went wrong while finding recipes. Please try again.",
      );
      setPhase("error");
    }
  }, []);

  const retry = useCallback(() => {
    if (lastRequestRef.current) {
      void run(lastRequestRef.current);
    }
  }, [run]);

  // Auto-dismiss the rate-limit toast after 6s -- same behavior the
  // pre-streaming mutation-based flow had. Scheduling the clear inside a
  // `setTimeout` callback (rather than calling `setRateLimitMessage`
  // directly in the effect body) keeps this out of
  // `react-hooks/set-state-in-effect`: this effect only *subscribes* to a
  // timer, it doesn't synchronously derive one piece of state from another.
  useEffect(() => {
    if (!rateLimitMessage) {
      return;
    }
    const timeout = setTimeout(() => setRateLimitMessage(null), 6000);
    return () => clearTimeout(timeout);
  }, [rateLimitMessage]);

  return { events, phase, errorDetail, rateLimitMessage, result, run, retry };
}

export default function HomePage() {
  const [profile, setProfile] = useState<UserProfile>(() => toUserProfile(DEFAULT_PROFILE_FORM_VALUE));
  const [pantryState, setPantryState] = useState<PantryState>({
    typedIngredients: "",
    cuisine: null,
    mealType: "dinner",
    confirmedInventory: [],
  });
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_COUNT);

  const stream = useRecommendStream();
  const isPending = stream.phase === "streaming";

  function handleFindRecipes() {
    setVisibleCount(INITIAL_VISIBLE_COUNT);
    const request: RecommendationRequest = {
      input_type: "text",
      typed_ingredients: pantryState.typedIngredients || null,
      confirmed_inventory:
        pantryState.confirmedInventory.length > 0 ? pantryState.confirmedInventory : null,
      user_profile: profile,
      cuisine_preference: pantryState.cuisine,
      meal_type: pantryState.mealType,
    };
    void stream.run(request);
  }

  const result = stream.result;

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        <ProfileForm onProfileChange={setProfile} />
        <PantryInput onChange={setPantryState} />
        <button
          type="button"
          onClick={handleFindRecipes}
          disabled={isPending}
          className="rounded-md bg-cast-iron px-4 py-2.5 text-sm font-semibold text-porcelain disabled:opacity-50"
        >
          {isPending ? "Finding recipes…" : "Find recipes"}
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {stream.rateLimitMessage && (
          <div className="rounded-md border border-honey-dark bg-honey/15 px-3 py-2 text-sm text-honey-dark">
            {stream.rateLimitMessage}
          </div>
        )}

        {(stream.phase === "streaming" || stream.phase === "error") && (
          <RunProgressTimeline
            events={stream.events}
            phase={stream.phase}
            errorDetail={stream.errorDetail}
            onRetry={stream.retry}
          />
        )}

        {stream.phase === "idle" && result && (
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
                {(result.recommendations ?? []).slice(0, visibleCount).map((recommendation) => (
                  <RecipeCard
                    key={recommendation.recipe.recipe_id}
                    recipe={recommendation.recipe}
                    score={recommendation.score}
                    explanation={recommendation.explanation}
                  />
                ))}

                {visibleCount < (result.recommendations ?? []).length && (
                  <button
                    type="button"
                    onClick={() =>
                      setVisibleCount((current) =>
                        Math.min(current + VISIBLE_COUNT_STEP, (result.recommendations ?? []).length),
                      )
                    }
                    className="rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40 disabled:opacity-50"
                  >
                    See more
                  </button>
                )}
              </div>
            )}

            <ShoppingList items={result.shopping_list ?? []} />
            <TasteProfilePanel tasteProfile={result.taste_profile} />
            <WasteNudges nudges={result.waste_nudges} />
          </>
        )}

        {stream.phase === "idle" && !result && (
          <p className="text-sm text-cast-iron/60">
            Add what's in your kitchen and set your profile, then find recipes.
          </p>
        )}

        <DebugDrawer response={result ?? null} />
      </div>
    </div>
  );
}
