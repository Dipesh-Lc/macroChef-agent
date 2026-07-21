import { useState } from "react";
import { postFeedback } from "../api/endpoints";
import type { MealRecommendation } from "../api/types";
import { batchTotalsLine } from "../lib/batchTotals";
import { macroDisplay } from "../lib/macroDisplay";
import { recipeImageUrl } from "../lib/placeholderImage";
import { ingredientDisplay, scaleIngredients } from "../lib/scaling";
import { NutritionBreakdown } from "./NutritionBreakdown";
import { SubstitutionNoteCard } from "./SubstitutionNoteCard";
import { TrustBadge } from "./TrustBadge";

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
  const { recipe, score, explanation } = recommendation;
  const [imageFailed, setImageFailed] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
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

  const scoreTiles: { label: string; value: number }[] = [
    { label: "Final", value: score.final_score },
    { label: "Pantry", value: score.pantry_match_score },
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
          <div className="flex items-start justify-between gap-2">
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
            <TrustBadge state={macros.state} />
          </div>

          <p className="font-mono text-sm text-cast-iron">{macros.badgeText}</p>

          <p className="text-sm text-cast-iron/80">
            {recipe.description ??
              "A practical meal match based on your pantry, nutrition targets, and hard safety constraints."}
          </p>
          <p className="text-sm italic text-cast-iron/70">{explanation}</p>

          <div className="grid grid-cols-3 gap-2 text-xs text-cast-iron/70 sm:grid-cols-6">
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

          <div className="flex flex-col gap-1.5">
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

          <FeedbackButtons recipeId={recipe.recipe_id} />
        </div>
      </div>
    </article>
  );
}
