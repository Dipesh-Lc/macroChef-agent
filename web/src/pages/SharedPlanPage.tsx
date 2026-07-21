import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, NotFoundError } from "../api/client";
import { getSharedPlan } from "../api/endpoints";
import type { PublicDayPlan, PublicRecipe, SharedPlanView } from "../api/types";
import { ComingSoonPage } from "../components/ComingSoonPage";
import { PlanMacroSummary } from "../components/PlanMacroSummary";
import { SubstitutionNoteCard } from "../components/SubstitutionNoteCard";
import { TrustBadge } from "../components/TrustBadge";
import { macroDisplay } from "../lib/macroDisplay";
import { ingredientDisplay } from "../lib/scaling";

/**
 * Public, UNAUTHENTICATED viewer for `GET /share/{id}` (roadmap item
 * "Shareable plan URLs", Phase 4 item 4). Deliberately makes NO fetch call
 * that sends credentials or bootstraps a session -- `getSharedPlan`
 * (api/endpoints.ts) hits `apiRequest` without `sessionRequired`, so no
 * `POST /session` round-trip ever happens on this page, and this page must
 * therefore render fully useful for a visitor with no MacroChef cookie at
 * all (see the route's own docstring in `app.api.routes_share`).
 */

type LoadState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error"; message: string }
  | { status: "ready"; view: SharedPlanView };

function PublicRecipeView({ recipe }: { recipe: PublicRecipe }) {
  const macros = macroDisplay(recipe);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const metaParts = [
    recipe.cuisine ?? "Any cuisine",
    recipe.meal_type ?? "meal",
    recipe.cook_time_min ? `${recipe.cook_time_min} min` : "time unknown",
  ];

  return (
    <article className="flex flex-col gap-3 rounded-lg border border-sage-line bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1 className="font-display text-xl font-semibold text-cast-iron">{recipe.title}</h1>
          <p className="text-sm text-cast-iron/70">{metaParts.join(" · ")}</p>
        </div>
        <TrustBadge state={macros.state} />
      </div>

      <p className="font-mono text-sm text-cast-iron">{macros.badgeText}</p>

      {recipe.description && <p className="text-sm text-cast-iron/80">{recipe.description}</p>}

      <div>
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">Ingredients</span>
        <ul className="mt-1 flex flex-col gap-1 text-sm text-cast-iron">
          {(recipe.ingredients ?? []).length === 0 ? (
            <li className="text-cast-iron/60">No structured ingredient amounts recorded.</li>
          ) : (
            (recipe.ingredients ?? []).map((ingredient, index) => (
              <li key={`${ingredient.name}-${index}`} className="border-b border-sage-line/60 pb-1 last:border-none">
                {ingredientDisplay(ingredient)}
              </li>
            ))
          )}
        </ul>
      </div>

      {recipe.substitution_note && <SubstitutionNoteCard note={recipe.substitution_note} />}

      {(recipe.instructions ?? []).length > 0 && (
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
      )}
    </article>
  );
}

// `PublicDayPlan` (unlike `DayPlan`) has no `trusted_pool_size` -- see that
// schema's docstring -- but is otherwise identical, including `items`.
function SharedDayPlanView({ dayPlan }: { dayPlan: PublicDayPlan }) {
  return (
    <>
      <PlanMacroSummary plan={dayPlan} />
      <section className="rounded-lg border border-sage-line bg-white p-4">
        <h2 className="font-display text-base font-semibold text-cast-iron">Meals</h2>
        <ul className="mt-2 flex flex-col">
          {(dayPlan.items ?? []).map((item) => (
            <li
              key={item.recipe_id}
              className="flex items-center justify-between gap-3 border-b border-sage-line/60 py-2 last:border-none"
            >
              <span className="text-sm text-cast-iron">{item.title}</span>
              <span className="font-mono text-sm text-cast-iron/70">
                {item.servings}x serving{item.servings === 1 ? "" : "s"}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

export default function SharedPlanPage() {
  const { shareId } = useParams<{ shareId: string }>();
  // Lazy initializer folds the "no :shareId param at all" case into the
  // initial render (never reachable via the registered `/shared/:shareId`
  // route, but defensive) instead of a synchronous `setState` inside the
  // effect below.
  const [state, setState] = useState<LoadState>(() =>
    shareId ? { status: "loading" } : { status: "not-found" },
  );

  useEffect(() => {
    if (!shareId) {
      return;
    }
    let cancelled = false;
    getSharedPlan(shareId)
      .then((view) => {
        if (!cancelled) {
          setState({ status: "ready", view });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (error instanceof NotFoundError) {
          setState({ status: "not-found" });
        } else if (error instanceof ApiError) {
          setState({ status: "error", message: error.message });
        } else {
          setState({ status: "error", message: "Could not load this shared plan. Please try again." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [shareId]);

  if (state.status === "loading") {
    return (
      <div className="h-40 animate-pulse rounded-lg border border-dashed border-sage-line bg-white" />
    );
  }

  if (state.status === "not-found") {
    return (
      <ComingSoonPage
        title="This shared plan wasn't found"
        message="The link may be mistyped, or the plan it pointed to was revoked. Shared links never expose whose plan this was."
      />
    );
  }

  if (state.status === "error") {
    return <ComingSoonPage title="Could not load this shared plan" message={state.message} />;
  }

  const { view } = state;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-md border border-honey-dark bg-honey/15 px-3 py-2 text-sm text-cast-iron">
        {view.disclaimer}
      </div>

      {view.plan_type === "recipe" && <PublicRecipeView recipe={view.content as PublicRecipe} />}

      {view.plan_type === "day" && (
        <SharedDayPlanView dayPlan={view.content as PublicDayPlan} />
      )}

      {(view.plan_type === "batch" || view.plan_type === "week") && (
        <ComingSoonPage
          title="Not yet supported in this preview"
          message={`Viewing a shared ${view.plan_type === "batch" ? "batch" : "weekly"} plan is on its way in a future update.`}
        />
      )}
    </div>
  );
}
