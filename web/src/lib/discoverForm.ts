/**
 * Field set, option lists, and defaults for `DiscoverForm.tsx`, ported from
 * `frontend/components/library_builder_form.py`'s
 * `render_library_builder_form` -- same options, same Streamlit 0-based
 * `index=N` defaults. Kept in its own module (mirroring `lib/profile.ts`'s
 * precedent) so `DiscoverForm.tsx` only exports the component itself --
 * `react-refresh/only-export-components` flags a component file that also
 * exports plain functions/constants.
 */
import type { RecipeDiscoveryRequest } from "../api/types";

export const CUISINE_OPTIONS = [
  "Italian",
  "Indian",
  "Japanese",
  "Chinese",
  "Mexican",
  "Mediterranean",
  "American",
];
export const DEFAULT_CUISINES = ["Japanese", "Indian"];

export const MEAL_TYPE_OPTIONS = ["Any", "breakfast", "lunch", "dinner"];
export const DEFAULT_MEAL_TYPE = "dinner"; // index=3

export const DIET_TYPE_OPTIONS = [
  "Any",
  "high-protein",
  "vegetarian",
  "vegan",
  "dairy-free",
  "gluten-free",
];
export const DEFAULT_DIET_TYPE = "high-protein"; // index=1

export const DIFFICULTY_OPTIONS = ["Any", "easy", "medium", "hard"];
export const DEFAULT_DIFFICULTY = "easy"; // index=1

// `RecipeDiscoveryRequest.max_cook_time_min` has no upper bound in the
// schema (ge=0 only) -- these are just the Streamlit slider's own
// min/max/step/default, not a wire-format constraint.
export const MIN_COOK_TIME = 10;
export const MAX_COOK_TIME = 90;
export const COOK_TIME_STEP = 5;
export const DEFAULT_COOK_TIME = 35;

// `RecipeDiscoveryRequest.count` (ge=1, le=50) -- these are the Streamlit
// `select_slider`'s own discrete options, all within that range.
export const COUNT_OPTIONS = [5, 10, 15, 20];
export const DEFAULT_COUNT = 10;

// `RecipeDiscoveryRequest.source_mode` (`SourceMode` in
// app/schemas/library.py) -- verified against the Literal, not guessed.
export const SOURCE_MODE_OPTIONS: RecipeDiscoveryRequest["source_mode"][] = [
  "mock",
  "llm",
  "external",
  "hybrid",
];
export const DEFAULT_SOURCE_MODE: RecipeDiscoveryRequest["source_mode"] = "mock";

export interface DiscoverFormValue {
  cuisines: string[];
  mealType: string;
  dietType: string;
  difficulty: string;
  maxCookTimeMin: number;
  count: number;
  allergies: string[];
  excludedIngredients: string[];
  extraPreferences: string;
  sourceMode: RecipeDiscoveryRequest["source_mode"];
  homeCookable: boolean;
}

export function defaultDiscoverFormValue(): DiscoverFormValue {
  return {
    cuisines: DEFAULT_CUISINES,
    mealType: DEFAULT_MEAL_TYPE,
    dietType: DEFAULT_DIET_TYPE,
    difficulty: DEFAULT_DIFFICULTY,
    maxCookTimeMin: DEFAULT_COOK_TIME,
    count: DEFAULT_COUNT,
    allergies: [],
    excludedIngredients: [],
    extraPreferences: "",
    sourceMode: DEFAULT_SOURCE_MODE,
    homeCookable: true,
  };
}

/** Builds the exact `RecipeDiscoveryRequest` wire body from form state. */
export function toDiscoveryRequest(value: DiscoverFormValue): RecipeDiscoveryRequest {
  return {
    cuisines: value.cuisines,
    meal_type: value.mealType === "Any" ? null : value.mealType,
    diet_type: value.dietType === "Any" ? null : value.dietType,
    max_cook_time_min: value.maxCookTimeMin,
    difficulty: value.difficulty === "Any" ? null : value.difficulty,
    count: value.count,
    home_cookable: value.homeCookable,
    excluded_ingredients: value.excludedIngredients,
    allergies: value.allergies,
    extra_preferences: value.extraPreferences.trim() ? value.extraPreferences.trim() : null,
    source_mode: value.sourceMode,
  };
}

export function toggleCuisine(current: string[], cuisine: string): string[] {
  return current.includes(cuisine)
    ? current.filter((item) => item !== cuisine)
    : [...current, cuisine];
}
