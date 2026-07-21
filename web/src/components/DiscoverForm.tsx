import { useState } from "react";
import type { RecipeDiscoveryRequest } from "../api/types";
import {
  COOK_TIME_STEP,
  COUNT_OPTIONS,
  CUISINE_OPTIONS,
  DIET_TYPE_OPTIONS,
  DIFFICULTY_OPTIONS,
  MAX_COOK_TIME,
  MEAL_TYPE_OPTIONS,
  MIN_COOK_TIME,
  SOURCE_MODE_OPTIONS,
  defaultDiscoverFormValue,
  toDiscoveryRequest,
  toggleCuisine,
  type DiscoverFormValue,
} from "../lib/discoverForm";
import { TagInput } from "./TagInput";

/**
 * Port of `frontend/components/library_builder_form.py`'s
 * `render_library_builder_form` -- same fields, same option lists, same
 * defaults (see `lib/discoverForm.ts` for the options/defaults themselves).
 * Free-text CSV fields (allergens, excluded ingredients) become `TagInput`
 * chips instead of a comma-separated text box -- same underlying
 * `list[str]`, friendlier input, matching `ProfileForm`'s precedent for
 * free-text allergy/dislike vocabulary (see that component's docstring).
 */
export function DiscoverForm({
  onDiscover,
  isPending,
}: {
  onDiscover: (request: RecipeDiscoveryRequest) => void;
  isPending: boolean;
}) {
  const [value, setValue] = useState<DiscoverFormValue>(() => defaultDiscoverFormValue());

  function update<K extends keyof DiscoverFormValue>(key: K, next: DiscoverFormValue[K]) {
    setValue((current) => ({ ...current, [key]: next }));
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-sage-line bg-white p-4">
      <div>
        <h2 className="font-display text-base font-semibold text-cast-iron">Discover recipes</h2>
        <p className="text-xs text-cast-iron/60">
          Find candidate recipes to review and save into your library.
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
                  active
                    ? "border-basil bg-basil/10 text-basil"
                    : "border-sage-line text-cast-iron/70"
                }`}
              >
                {cuisine}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Meal type</span>
          <select
            value={value.mealType}
            onChange={(event) => update("mealType", event.target.value)}
            className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
          >
            {MEAL_TYPE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Diet type</span>
          <select
            value={value.dietType}
            onChange={(event) => update("dietType", event.target.value)}
            className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
          >
            {DIET_TYPE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Difficulty</span>
          <select
            value={value.difficulty}
            onChange={(event) => update("difficulty", event.target.value)}
            className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
          >
            {DIFFICULTY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
            Max cook time ({value.maxCookTimeMin} min)
          </span>
          <input
            type="range"
            min={MIN_COOK_TIME}
            max={MAX_COOK_TIME}
            step={COOK_TIME_STEP}
            value={value.maxCookTimeMin}
            onChange={(event) => update("maxCookTimeMin", Number(event.target.value))}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
            Recipes to discover
          </span>
          <select
            value={value.count}
            onChange={(event) => update("count", Number(event.target.value))}
            className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
          >
            {COUNT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      <TagInput
        label="Allergens to avoid"
        placeholder="e.g. peanut, shellfish"
        items={value.allergies}
        onChange={(items) => update("allergies", items)}
      />

      <TagInput
        label="Excluded ingredients"
        placeholder="e.g. cilantro, mushrooms"
        items={value.excludedIngredients}
        onChange={(items) => update("excludedIngredients", items)}
      />

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">
          Extra preferences
        </span>
        <textarea
          value={value.extraPreferences}
          onChange={(event) => update("extraPreferences", event.target.value)}
          rows={3}
          placeholder="home-cookable, no deep frying, minimal equipment"
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-cast-iron/60">Source mode</span>
        <select
          value={value.sourceMode}
          onChange={(event) =>
            update("sourceMode", event.target.value as RecipeDiscoveryRequest["source_mode"])
          }
          className="rounded-md border border-sage-line bg-white px-2 py-1.5 text-sm text-cast-iron focus:border-basil"
        >
          {SOURCE_MODE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 text-sm text-cast-iron">
        <input
          type="checkbox"
          checked={value.homeCookable}
          onChange={(event) => update("homeCookable", event.target.checked)}
        />
        Prioritize home-cookable recipes
      </label>

      <button
        type="button"
        onClick={() => onDiscover(toDiscoveryRequest(value))}
        disabled={isPending}
        className="rounded-md bg-cast-iron px-4 py-2.5 text-sm font-semibold text-porcelain disabled:opacity-50"
      >
        {isPending ? "Discovering recipes…" : "Discover recipes"}
      </button>
    </div>
  );
}
