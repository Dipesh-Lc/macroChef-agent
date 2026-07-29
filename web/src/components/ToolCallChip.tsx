import { useState } from "react";
import type { FoodMacros } from "../api/types";

/**
 * Inline chip for one Chef-agent tool call (ROADMAP.md Step 4.3). Renders
 * ONLY what the deterministic backend already decided/returned -- never its
 * own safety wording (CLAUDE.md invariant #1). `check_recipe_safety`'s
 * pass/fail line reads `result.is_valid`/`result.rejection_reason` verbatim;
 * `ground_nutrition`'s status line reads `raw.status` verbatim. Every other
 * tool's expanded detail is a thin, non-judgmental listing of the recipes/
 * data the tool call surfaced.
 */

export interface ToolResultData {
  summary: string;
  raw: Record<string, unknown>;
}

export interface ToolCallChipData {
  callId: string;
  tool: string;
  /** Ephemeral human one-liner from the LIVE `tool_call` SSE event's
   * `args_summary` (`app.agent.chef_agent._args_summary`) -- never persisted
   * (see `app.agent.memory.persist_turn`'s docstring), so a chip rebuilt
   * from `GET /chat/{thread_id}` history never has this set. Only shown
   * while `result` is still `undefined` (the call is in flight). */
  argsSummary?: string;
  /** `undefined` while the call is still in flight -- live only. A chip
   * rebuilt from history always has a `result`, since `GET
   * /chat/{thread_id}` only ever returns completed turns. */
  result?: ToolResultData;
  /** `ToolResult.ok` -- whether the tool call ITSELF succeeded (bad args,
   * recipe not found, ...). A safety REJECTION (e.g. `check_recipe_safety`
   * finding an allergy violation) is still `ok=true`; that verdict lives in
   * `result.raw`, not here. Absent for a still-in-flight live chip. */
  ok?: boolean;
  error?: string | null;
}

const TOOL_ICONS: Record<string, string> = {
  search_recipes: "🔍",
  check_recipe_safety: "🛡",
  ground_nutrition: "🧪",
  propose_substitutions: "🔁",
  build_day_plan: "🗓",
  get_user_context: "🧠",
  remember: "📝",
};

interface CheckSafetyResultRow {
  recipe_id?: string;
  result?: { is_valid?: boolean; rejection_reason?: string | null };
}

function CheckSafetyDetail({ raw }: { raw: Record<string, unknown> }) {
  const rows = Array.isArray(raw.results) ? (raw.results as CheckSafetyResultRow[]) : [];
  if (rows.length === 0) {
    return <p className="text-xs text-cast-iron/60">No recipes were checked.</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {rows.map((row, index) => {
        const isValid = row.result?.is_valid === true;
        return (
          <li
            key={row.recipe_id ?? index}
            className="flex items-start justify-between gap-3 font-mono text-xs"
          >
            <span className="text-cast-iron/70">{row.recipe_id ?? "unknown recipe"}</span>
            <span className={isValid ? "shrink-0 text-basil" : "shrink-0 text-chili"}>
              {isValid ? "Safe" : `Rejected — ${row.result?.rejection_reason ?? "unknown reason"}`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// Same trust-state palette `lib/macroDisplay.ts`'s "grounded"/"partial"/
// "unknown" states use elsewhere in the app (basil = trusted, honey = a
// disclosed undercount, muted cast-iron = no verified number at all) --
// design call for this step, not a pre-existing shared constant, since this
// tool's `status` string comes from `app.agent.tools._ground_nutrition`
// (via `nutrition_view.macro_display_state`), not a typed `Recipe.nutrition`
// object `macroDisplayState()` itself could run on.
const GROUND_NUTRITION_STATUS_STYLES: Record<string, string> = {
  grounded: "text-basil",
  partial: "text-honey-dark",
  unknown: "text-cast-iron/60",
};

function GroundNutritionDetail({ raw }: { raw: Record<string, unknown> }) {
  const status = typeof raw.status === "string" ? raw.status : "unknown";
  const perServing = (raw.per_serving ?? null) as FoodMacros | null;
  const ungrounded = Array.isArray(raw.ungrounded_ingredients)
    ? (raw.ungrounded_ingredients as string[])
    : [];

  return (
    <div className="flex flex-col gap-1.5 text-xs">
      <span
        className={`font-mono font-semibold uppercase tracking-wide ${
          GROUND_NUTRITION_STATUS_STYLES[status] ?? "text-cast-iron/60"
        }`}
      >
        {status}
      </span>
      {perServing && (
        <p className="font-mono text-cast-iron">
          {Math.round(perServing.calories)} kcal | {Math.round(perServing.protein_g)}P /{" "}
          {Math.round(perServing.carbs_g)}C / {Math.round(perServing.fat_g)}F
        </p>
      )}
      {ungrounded.length > 0 && (
        <p className="text-cast-iron/60">Unverified: {ungrounded.join(", ")}</p>
      )}
    </div>
  );
}

interface RecipeRowLike {
  recipe_id?: string;
  title?: string;
}

function RecipeListDetail({
  rows,
  onViewRecipe,
}: {
  rows: RecipeRowLike[];
  onViewRecipe?: (recipeId: string) => void;
}) {
  if (rows.length === 0) {
    return <p className="text-xs text-cast-iron/60">No recipes.</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {rows.map((row, index) => (
        <li
          key={row.recipe_id ?? index}
          className="flex items-center justify-between gap-3 text-xs"
        >
          <span className="truncate text-cast-iron">{row.title ?? row.recipe_id ?? "Untitled"}</span>
          {onViewRecipe && row.recipe_id && (
            <button
              type="button"
              onClick={() => onViewRecipe(row.recipe_id as string)}
              className="shrink-0 text-basil underline underline-offset-2"
            >
              View recipe
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

function ToolResultDetail({
  tool,
  result,
  onViewRecipe,
}: {
  tool: string;
  result: ToolResultData;
  onViewRecipe?: (recipeId: string) => void;
}) {
  const raw = result.raw ?? {};

  if (tool === "check_recipe_safety") {
    return <CheckSafetyDetail raw={raw} />;
  }
  if (tool === "ground_nutrition") {
    return <GroundNutritionDetail raw={raw} />;
  }
  if (tool === "search_recipes" && Array.isArray(raw.recipes)) {
    return <RecipeListDetail rows={raw.recipes as RecipeRowLike[]} onViewRecipe={onViewRecipe} />;
  }
  if (tool === "propose_substitutions" && Array.isArray(raw.variants)) {
    return <RecipeListDetail rows={raw.variants as RecipeRowLike[]} onViewRecipe={onViewRecipe} />;
  }
  if (tool === "build_day_plan" && Array.isArray(raw.items)) {
    return <RecipeListDetail rows={raw.items as RecipeRowLike[]} onViewRecipe={onViewRecipe} />;
  }
  // get_user_context/remember (and any unrecognized tool): a plain summary
  // line is enough -- lower-stakes, no special card (per the task spec's
  // own per-tool rendering rules).
  return <p className="text-xs text-cast-iron/70">{result.summary}</p>;
}

export function ToolCallChip({
  call,
  onViewRecipe,
}: {
  call: ToolCallChipData;
  onViewRecipe?: (recipeId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const icon = TOOL_ICONS[call.tool] ?? "🔧";
  const pending = call.result === undefined;
  const failed = call.ok === false;

  return (
    <div
      className={`w-fit max-w-full rounded-md border text-sm ${
        failed ? "border-chili/60 bg-chili/5" : "border-sage-line bg-white"
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        disabled={pending}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left disabled:cursor-default"
      >
        <span aria-hidden="true">{icon}</span>
        {pending ? (
          <>
            {/* `animate-pulse` is neutralized under `prefers-reduced-motion`
                by the global CSS reset -- same convention `RunProgressTimeline`'s
                `StatusDot` already relies on. */}
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-honey"
            />
            <span className="italic text-cast-iron/60">
              {call.argsSummary ?? `Calling ${call.tool}…`}
            </span>
          </>
        ) : (
          <span className={failed ? "text-chili" : "text-cast-iron"}>
            <span className="font-medium">{call.tool}</span>
            {" → "}
            {call.result?.summary}
          </span>
        )}
      </button>

      {expanded && call.result && (
        <div className="border-t border-sage-line/60 px-3 py-2">
          <ToolResultDetail tool={call.tool} result={call.result} onViewRecipe={onViewRecipe} />
        </div>
      )}
    </div>
  );
}
