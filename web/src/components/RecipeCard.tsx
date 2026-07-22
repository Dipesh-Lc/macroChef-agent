import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, RateLimitError } from "../api/client";
import { getDetailedInstructions, postFeedback } from "../api/endpoints";
import type { MealRecommendation } from "../api/types";
import { batchTotalsLine } from "../lib/batchTotals";
import { macroDisplay } from "../lib/macroDisplay";
import { recipeImageUrl } from "../lib/placeholderImage";
import { ingredientDisplay, scaleIngredients } from "../lib/scaling";
import { NutritionBreakdown } from "./NutritionBreakdown";
import { SubstitutionNoteCard } from "./SubstitutionNoteCard";

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
 * "Get detailed instructions" -- a NEW, separate control from the existing
 * "Show/Hide instructions" raw-list toggle above (left untouched). Fires a
 * TanStack Query mutation against POST /recipes/instructions (see
 * app.services.model_provider.generate_detailed_instructions_with_provider_chain),
 * a phrasing/elaboration-only call: it never adds/removes/substitutes an
 * ingredient and never states a nutrition or allergy/diet safety claim --
 * see that function's docstring for the deterministic guardrails baked into
 * the backend prompt. This component makes no safety decision of its own.
 */
function DetailedInstructions({
  title,
  ingredients,
  instructions,
  servings,
  cuisine,
}: {
  title: string;
  ingredients: string[];
  instructions: string[];
  servings?: number | null;
  cuisine?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      getDetailedInstructions({
        title,
        ingredients,
        instructions,
        servings: servings ?? null,
        cuisine: cuisine ?? null,
      }),
  });

  function handleClick() {
    setOpen(true);
    if (!mutation.isSuccess) {
      mutation.mutate();
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        disabled={mutation.isPending}
        className="text-xs font-medium uppercase tracking-wide text-basil underline underline-offset-2 disabled:opacity-50"
      >
        {mutation.isPending ? "Generating…" : "Get detailed instructions"}
      </button>

      {open && mutation.isPending && (
        <p className="mt-2 text-sm text-cast-iron/60">Writing detailed, step-by-step instructions…</p>
      )}

      {open && mutation.isError && (
        <div className="mt-2 rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          {friendlyErrorMessage(mutation.error, "Could not generate detailed instructions. Please try again.")}
        </div>
      )}

      {open && mutation.isSuccess && (
        <div className="mt-2 flex flex-col gap-1 rounded-md border border-basil/30 bg-basil/5 p-3">
          <span className="text-xs font-medium uppercase tracking-wide text-basil">Detailed steps</span>
          {!mutation.data.generated && mutation.data.provider_note && (
            <p className="text-xs italic text-cast-iron/60">{mutation.data.provider_note}</p>
          )}
          <ol className="mt-1 flex list-inside list-decimal flex-col gap-1 text-sm text-cast-iron">
            {(mutation.data.steps ?? []).map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function IngredientChips({ items, variant }: { items: string[]; variant: "used" | "missing" }) {
  if (items.length === 0) {
    return null;
  }
  const chipClass =
    variant === "used"
      ? "rounded-full border border-basil px-2 py-0.5 text-xs text-basil"
      : "rounded-full border border-dashed border-sage-line px-2 py-0.5 text-xs text-cast-iron/60";
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={item} className={chipClass}>
          {item}
        </span>
      ))}
    </div>
  );
}

type FeedbackType = "liked" | "disliked" | "cooked";

const FEEDBACK_BUTTONS: { type: FeedbackType; label: string }[] = [
  { type: "liked", label: "Like" },
  { type: "disliked", label: "Dislike" },
  { type: "cooked", label: "Cooked" },
];

function FeedbackButtons({ recipeId }: { recipeId: string }) {
  const [pressed, setPressed] = useState<FeedbackType | null>(null);
  const [pending, setPending] = useState<FeedbackType | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick(type: FeedbackType) {
    setPending(type);
    setError(null);
    const previousPressed = pressed;
    setPressed(type); // optimistic
    try {
      await postFeedback({ recipe_id: recipeId, feedback_type: type });
    } catch {
      setPressed(previousPressed);
      setError("Could not save feedback — please try again.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex gap-2">
        {FEEDBACK_BUTTONS.map(({ type, label }) => (
          <button
            key={type}
            type="button"
            onClick={() => handleClick(type)}
            disabled={pending !== null}
            className={`rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
              pressed === type ? "border-basil bg-basil/10 text-basil" : "border-sage-line text-cast-iron/70"
            }`}
          >
            {pending === type ? "Saving…" : label}
          </button>
        ))}
      </div>
      {error && <p className="text-xs text-chili">{error}</p>}
    </div>
  );
}

export function RecipeCard({ recommendation }: { recommendation: MealRecommendation }) {
  const { recipe, score } = recommendation;
  const [imageFailed, setImageFailed] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [scoreDetailsOpen, setScoreDetailsOpen] = useState(false);
  const macros = macroDisplay(recipe);
  const imageUrl = recipeImageUrl(recipe);
  const metaParts = [
    recipe.cuisine ?? "Any cuisine",
    recipe.meal_type ?? "meal",
    recipe.cook_time_min ? `${recipe.cook_time_min} min` : "time unknown",
  ];

  // B2 serving scaler, ported from the Streamlit range/default logic in
  // `recommendation_cards.py`: default is the recipe's own serving count (or
  // 1 if unset), range is 1..max(8, defaultServings) so a recipe that
  // naturally serves more than 8 is still reachable at its own default.
  const defaultServings = recipe.servings ?? 1;
  const maxServings = Math.max(8, defaultServings);
  const [targetServings, setTargetServings] = useState(defaultServings);
  const scaleFactor = targetServings / defaultServings;
  const scaledIngredients = scaleIngredients(recipe.ingredients ?? [], scaleFactor);
  const batchLine = batchTotalsLine(recipe, targetServings);

  // The "Pantry" tile (score.pantry_match_score) is intentionally dropped
  // from this list -- the always-visible "Matching Info" ingredient chips
  // above already convey pantry match at a glance, so it would be
  // redundant inside the (now click-to-reveal) score-details grid below.
  // "Pantry mass" is kept since it's a distinct, non-redundant signal (the
  // mass-weighted coverage fraction, not a duplicate of the chips).
  const scoreTiles: { label: string; value: number }[] = [
    { label: "Final", value: score.final_score },
    { label: "Macros", value: score.macro_fit_score },
    { label: "Time", value: score.time_score },
    { label: "Preference", value: score.preference_score },
    { label: "Pantry mass", value: score.pantry_mass_coverage },
  ];

  return (
    <article className="overflow-hidden rounded-lg border border-sage-line bg-white shadow-sm">
      <div className="grid gap-4 p-4 sm:grid-cols-[160px_1fr]">
        {imageFailed ? (
          <div className="flex h-[120px] w-full items-center justify-center rounded-md bg-basil/10 text-center text-xs text-basil sm:h-full">
            {recipe.cuisine ?? "MacroChef"} recipe
          </div>
        ) : (
          <img
            src={imageUrl}
            alt={recipe.title}
            onError={() => setImageFailed(true)}
            className="h-[120px] w-full rounded-md object-cover sm:h-full"
          />
        )}

        <div className="flex flex-col gap-2">
          <div>
            <h3 className="font-display text-lg font-semibold text-cast-iron">{recipe.title}</h3>
            <p className="text-sm text-cast-iron/70">{metaParts.join(" · ")}</p>
            {recipe.restored_from_quarantine && (
              <span
                title="Recovered from an earlier import's quarantine after the 2026-07-19 corpus rebuild verified it against the original recipe page."
                className="mt-1 inline-flex w-fit items-center rounded-full border border-dashed border-honey-dark bg-honey/10 px-2 py-0.5 text-xs text-honey-dark"
              >
                Restored from source
              </span>
            )}
          </div>

          <p className="text-sm text-cast-iron/80">
            {recipe.description ??
              "A practical meal match based on your pantry, nutrition targets, and hard safety constraints."}
          </p>

          <p className="font-mono text-sm text-cast-iron">{macros.badgeText}</p>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
              Matching Info
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
              Used ingredients
            </span>
            <IngredientChips items={score.used_ingredients ?? []} variant="used" />
            <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">
              Missing ingredients
            </span>
            <IngredientChips items={score.missing_ingredients ?? []} variant="missing" />
          </div>

          <div className="flex flex-col gap-2 rounded-md border border-sage-line p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">Servings</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setTargetServings((value) => Math.max(1, value - 1))}
                  disabled={targetServings <= 1}
                  aria-label="Decrease servings"
                  className="h-6 w-6 rounded-md border border-sage-line text-sm text-cast-iron disabled:opacity-40"
                >
                  −
                </button>
                <span className="w-6 text-center font-mono text-sm text-cast-iron">{targetServings}</span>
                <button
                  type="button"
                  onClick={() => setTargetServings((value) => Math.min(maxServings, value + 1))}
                  disabled={targetServings >= maxServings}
                  aria-label="Increase servings"
                  className="h-6 w-6 rounded-md border border-sage-line text-sm text-cast-iron disabled:opacity-40"
                >
                  +
                </button>
              </div>
            </div>
            <ul className="flex flex-col gap-1 text-sm text-cast-iron">
              {scaledIngredients.length === 0 ? (
                <li className="text-cast-iron/60">No structured ingredient amounts recorded.</li>
              ) : (
                scaledIngredients.map((ingredient, index) => (
                  <li
                    key={`${ingredient.name}-${index}`}
                    className="border-b border-sage-line/60 pb-1 last:border-none"
                  >
                    {ingredientDisplay(ingredient)}
                  </li>
                ))
              )}
            </ul>
            {batchLine && <p className="font-mono text-xs text-cast-iron/70">{batchLine}</p>}
          </div>

          {/* Secondary/detail cluster: everything below is hidden behind a
              click (this toggle, the instructions toggle, "Get detailed
              instructions", or NutritionBreakdown's own internal toggle) --
              nothing here is part of the always-visible summary above. */}
          <div>
            <button
              type="button"
              onClick={() => setScoreDetailsOpen((value) => !value)}
              className="text-xs font-medium uppercase tracking-wide text-cast-iron/60 underline underline-offset-2"
            >
              {scoreDetailsOpen ? "Hide score details" : "Show score details"}
            </button>
            {scoreDetailsOpen && (
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-cast-iron/70 sm:grid-cols-5">
                {scoreTiles.map((tile) => (
                  <span
                    key={tile.label}
                    className="flex flex-col items-center rounded-md border border-sage-line px-2 py-1 text-center"
                  >
                    <span className="font-mono text-sm text-cast-iron">{Math.round(tile.value * 100)}%</span>
                    <span className="text-[0.65rem] text-cast-iron/50">{tile.label}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          <NutritionBreakdown recipe={recipe} />

          {recipe.substitution_note && <SubstitutionNoteCard note={recipe.substitution_note} />}

          <div>
            <button
              type="button"
              onClick={() => setInstructionsOpen((value) => !value)}
              className="text-xs font-medium uppercase tracking-wide text-cast-iron/60 underline underline-offset-2"
            >
              {instructionsOpen ? "Hide instructions" : "Show instructions"}
            </button>
            {instructionsOpen && (
              <ol className="mt-2 flex list-inside list-decimal flex-col gap-1 text-sm text-cast-iron">
                {(recipe.instructions ?? []).map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            )}
          </div>

          <DetailedInstructions
            title={recipe.title}
            ingredients={(recipe.ingredients ?? []).map((ingredient) => ingredientDisplay(ingredient))}
            instructions={recipe.instructions ?? []}
            servings={recipe.servings}
            cuisine={recipe.cuisine}
          />

          <FeedbackButtons recipeId={recipe.recipe_id} />
        </div>
      </div>
    </article>
  );
}
