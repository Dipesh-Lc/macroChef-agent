import { useState } from "react";
import type { RecipeSearchRequest } from "../api/types";
import { CUISINE_OPTIONS, DIET_TYPE_OPTIONS } from "../lib/discoverForm";
import {
  ANY_DIET_TYPE,
  defaultRecipeSearchFormValue,
  toSearchRequest,
  toggleCuisine,
  type RecipeSearchFormValue,
} from "../lib/recipeSearchForm";
import { TagInput } from "./TagInput";

/**
 * Recipe search/filter form for `RecipeSearchPage` -- submits a
 * `RecipeSearchRequest` to `POST /recipes/search` (via `searchRecipes` in
 * `api/endpoints.ts`). Deliberately local `useState` only, no localStorage
 * persistence (mirrors `DiscoverForm.tsx`'s convention for a browse/search
 * form, NOT `ProfileForm.tsx`'s persisted-profile convention -- a search
 * filter set is disposable per session, not a durable user setting).
 *
 * Reuses `CUISINE_OPTIONS`/`DIET_TYPE_OPTIONS` (`lib/discoverForm.ts`) and
 * `TagInput` (allergens-to-exclude) rather than redefining option lists or
 * a free-text CSV input -- see the task spec's "reuse, don't rebuild" list.
 *
 * SAFETY: this component makes no allergy/diet decision itself -- it only
 * builds the request; `POST /recipes/search` deterministically excludes
 * allergens/diet violations server-side (`app.api.routes_recommendations.
 * search_recipes`, via `app.services.constraint_engine.contains_allergen`/
 * `violates_diet_type`) before any result reaches this form's caller.
 */

function RangeField({
  label,
  minValue,
  maxValue,
  onMinChange,
  onMaxChange,
}: {
  label: string;
  minValue: string;
  maxValue: string;
  onMinChange: (value: string) => void;
  onMaxChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          min={0}
          value={minValue}
          onChange={(event) => onMinChange(event.target.value)}
          placeholder="Min"
          aria-label={`${label} minimum`}
          className="w-full rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-sm text-cast-iron focus:border-basil"
        />
        <span className="text-xs text-cast-iron/40">to</span>
        <input
          type="number"
          min={0}
          value={maxValue}
          onChange={(event) => onMaxChange(event.target.value)}
          placeholder="Max"
          aria-label={`${label} maximum`}
          className="w-full rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-sm text-cast-iron focus:border-basil"
        />
      </div>
    </div>
  );
}

export function RecipeSearchForm({
  onSearch,
  isPending,
}: {
  onSearch: (request: RecipeSearchRequest) => void;
  isPending: boolean;
}) {
  const [value, setValue] = useState<RecipeSearchFormValue>(() => defaultRecipeSearchFormValue());

  function update<K extends keyof RecipeSearchFormValue>(key: K, next: RecipeSearchFormValue[K]) {
    setValue((current) => ({ ...current, [key]: next }));
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-sage-line bg-white p-4">
      <div>
        <h2 className="font-display text-base font-semibold text-cast-iron">Search recipes</h2>
        <p className="text-xs text-cast-iron/60">
          Filter the recipe corpus by cuisine, allergens, diet, and macro ranges.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Cuisines</span>
        <div className="flex flex-wrap gap-2">
          {CUISINE_OPTIONS.map((cuisine) => {
            const active = value.cuisines.includes(cuisine);
            return (
              <button
                key={cuisine}
                type="button"
                onClick={() => update("cuisines", toggleCuisine(value.cuisines, cuisine))}
                aria-pressed={active}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                  active ? "border-basil bg-basil/10 text-basil" : "border-sage-line text-cast-iron/70"
                }`}
              >
                {cuisine}
              </button>
            );
          })}
        </div>
      </div>

      <TagInput
        label="Allergens to exclude"
        placeholder="e.g. peanut, shellfish"
        items={value.allergies}
        onChange={(items) => update("allergies", items)}
      />

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Diet type</span>
        <select
          value={value.dietType}
          onChange={(event) => update("dietType", event.target.value)}
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {[ANY_DIET_TYPE, ...DIET_TYPE_OPTIONS.filter((option) => option !== ANY_DIET_TYPE)].map(
            (option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ),
          )}
        </select>
      </label>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <RangeField
          label="Calories"
          minValue={value.calorieMin}
          maxValue={value.calorieMax}
          onMinChange={(next) => update("calorieMin", next)}
          onMaxChange={(next) => update("calorieMax", next)}
        />
        <RangeField
          label="Protein (g)"
          minValue={value.proteinMin}
          maxValue={value.proteinMax}
          onMinChange={(next) => update("proteinMin", next)}
          onMaxChange={(next) => update("proteinMax", next)}
        />
        <RangeField
          label="Carbs (g)"
          minValue={value.carbsMin}
          maxValue={value.carbsMax}
          onMinChange={(next) => update("carbsMin", next)}
          onMaxChange={(next) => update("carbsMax", next)}
        />
        <RangeField
          label="Fat (g)"
          minValue={value.fatMin}
          maxValue={value.fatMax}
          onMinChange={(next) => update("fatMin", next)}
          onMaxChange={(next) => update("fatMax", next)}
        />
      </div>

      <button
        type="button"
        onClick={() => onSearch(toSearchRequest(value))}
        disabled={isPending}
        className="rounded-md bg-cast-iron px-4 py-2.5 text-sm font-semibold text-porcelain disabled:opacity-50"
      >
        {isPending ? "Searching…" : "Search recipes"}
      </button>
    </div>
  );
}
