/**
 * Field set, defaults, and request-building logic for `RecipeSearchForm.tsx`
 * -- kept in its own module (mirroring `lib/discoverForm.ts`'s precedent) so
 * the component file only exports the component itself
 * (`react-refresh/only-export-components` flags a component file that also
 * exports plain functions/types).
 */
import type { RecipeSearchRequest } from "../api/types";

export const ANY_DIET_TYPE = "Any";

export interface RecipeSearchFormValue {
  cuisines: string[];
  allergies: string[];
  dietType: string;
  calorieMin: string;
  calorieMax: string;
  proteinMin: string;
  proteinMax: string;
  carbsMin: string;
  carbsMax: string;
  fatMin: string;
  fatMax: string;
}

export function defaultRecipeSearchFormValue(): RecipeSearchFormValue {
  return {
    cuisines: [],
    allergies: [],
    dietType: ANY_DIET_TYPE,
    calorieMin: "",
    calorieMax: "",
    proteinMin: "",
    proteinMax: "",
    carbsMin: "",
    carbsMax: "",
    fatMin: "",
    fatMax: "",
  };
}

/** Empty string -> undefined (field omitted from the wire body, same as
 * "no filter" -- `RecipeSearchRequest`'s min/max fields are all optional). */
function toOptionalNumber(raw: string): number | undefined {
  if (raw.trim() === "") {
    return undefined;
  }
  const parsed = Number(raw);
  return Number.isNaN(parsed) ? undefined : parsed;
}

export function toggleCuisine(current: string[], cuisine: string): string[] {
  return current.includes(cuisine)
    ? current.filter((item) => item !== cuisine)
    : [...current, cuisine];
}

export function toSearchRequest(value: RecipeSearchFormValue): RecipeSearchRequest {
  return {
    cuisines: value.cuisines.length > 0 ? value.cuisines : undefined,
    allergies: value.allergies.length > 0 ? value.allergies : undefined,
    diet_type: value.dietType === ANY_DIET_TYPE ? undefined : value.dietType,
    calorie_min: toOptionalNumber(value.calorieMin),
    calorie_max: toOptionalNumber(value.calorieMax),
    protein_min: toOptionalNumber(value.proteinMin),
    protein_max: toOptionalNumber(value.proteinMax),
    carbs_min: toOptionalNumber(value.carbsMin),
    carbs_max: toOptionalNumber(value.carbsMax),
    fat_min: toOptionalNumber(value.fatMin),
    fat_max: toOptionalNumber(value.fatMax),
  };
}
