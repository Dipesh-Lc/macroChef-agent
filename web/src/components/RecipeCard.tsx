import { useState } from "react";
import type { MealRecommendation } from "../api/types";
import { macroDisplay } from "../lib/macroDisplay";
import { recipeImageUrl } from "../lib/placeholderImage";
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

export function RecipeCard({ recommendation }: { recommendation: MealRecommendation }) {
  const { recipe, score, explanation } = recommendation;
  const [imageFailed, setImageFailed] = useState(false);
  const macros = macroDisplay(recipe);
  const imageUrl = recipeImageUrl(recipe);
  const metaParts = [
    recipe.cuisine ?? "Any cuisine",
    recipe.meal_type ?? "meal",
    recipe.cook_time_min ? `${recipe.cook_time_min} min` : "time unknown",
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
            </div>
            <TrustBadge state={macros.state} />
          </div>

          <p className="font-mono text-sm text-cast-iron">{macros.badgeText}</p>

          <p className="text-sm text-cast-iron/80">
            {recipe.description ??
              "A practical meal match based on your pantry, nutrition targets, and hard safety constraints."}
          </p>
          <p className="text-sm italic text-cast-iron/70">{explanation}</p>

          <div className="grid grid-cols-2 gap-2 text-xs text-cast-iron/70 sm:grid-cols-4">
            <span>Final: <span className="font-mono">{Math.round(score.final_score * 100)}%</span></span>
            <span>Pantry: <span className="font-mono">{Math.round(score.pantry_match_score * 100)}%</span></span>
            <span>Macros: <span className="font-mono">{Math.round(score.macro_fit_score * 100)}%</span></span>
            <span>Time: <span className="font-mono">{Math.round(score.time_score * 100)}%</span></span>
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
        </div>
      </div>
    </article>
  );
}
