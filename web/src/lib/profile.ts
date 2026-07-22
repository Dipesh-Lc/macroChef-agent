import type { UserProfile } from "../api/types";

// Mirrors the field set + defaults in `frontend/components/profile_form.py`
// (`render_profile_sidebar`). Diet options match
// `app.schemas.user.SUPPORTED_DIET_TYPES` exactly -- an unsupported value
// is rejected server-side (`UserProfile._validate_diet_type`), so this list
// must never drift from that set.
export const DIET_TYPE_OPTIONS = ["Any", "vegetarian", "vegan", "gluten-free", "dairy-free"] as const;
export type DietTypeOption = (typeof DIET_TYPE_OPTIONS)[number];

export const MAX_COOK_TIME_OPTIONS: { label: string; minutes: number | null }[] = [
  { label: "No limit", minutes: null },
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "45 min", minutes: 45 },
  { label: "60 min", minutes: 60 },
];

// UI-only -- NOT part of the UserProfile wire schema. Streamlit's own
// sidebar (`render_profile_sidebar`) computes this same selectbox value and
// never includes it in the returned profile dict either; ported here
// faithfully rather than invented.
export const SERVINGS_OPTIONS: { label: string; servings: number }[] = [
  { label: "1 person", servings: 1 },
  { label: "2 people", servings: 2 },
  { label: "4 people", servings: 4 },
];

export interface ProfileFormValue {
  allergies: string[];
  dislikedIngredients: string[];
  dietType: DietTypeOption;
  calories: number;
  caloriesEnabled: boolean;
  proteinG: number;
  proteinEnabled: boolean;
  carbsG: number;
  carbsEnabled: boolean;
  fatG: number;
  fatEnabled: boolean;
  fiberG: number;
  fiberEnabled: boolean;
  maxCookTimeMin: number | null;
  servings: number;
}

// Every macro target is OFF by default -- a new user sends no macro targets
// at all until they explicitly opt in, per the "all five OFF by default"
// requirement. `macro_fit_score` (app/services/nutrition_scorer.py) already
// treats an absent/`None`/`<=0` target as "not set" and returns a neutral
// 0.5 when none are set, so this needs no backend change.
export const DEFAULT_PROFILE_FORM_VALUE: ProfileFormValue = {
  allergies: [],
  dislikedIngredients: [],
  dietType: "Any",
  calories: 2000,
  caloriesEnabled: false,
  proteinG: 150,
  proteinEnabled: false,
  carbsG: 200,
  carbsEnabled: false,
  fatG: 65,
  fatEnabled: false,
  fiberG: 25,
  fiberEnabled: false,
  maxCookTimeMin: null,
  servings: 2,
};

export function toUserProfile(value: ProfileFormValue): UserProfile {
  return {
    user_id: "demo_user",
    allergies: value.allergies,
    disliked_ingredients: value.dislikedIngredients,
    diet_type: value.dietType === "Any" ? null : value.dietType,
    preferred_cuisines: [],
    macro_targets: {
      calories: value.caloriesEnabled ? value.calories : null,
      protein_g: value.proteinEnabled ? value.proteinG : null,
      carbs_g: value.carbsEnabled ? value.carbsG : null,
      fat_g: value.fatEnabled ? value.fatG : null,
      fiber_g: value.fiberEnabled ? value.fiberG : null,
    },
    max_cook_time_min: value.maxCookTimeMin,
  };
}

export const PROFILE_FORM_STORAGE_KEY = "macrochef.profileForm.v1";

export function loadProfileFormValue(): ProfileFormValue {
  if (typeof window === "undefined") {
    return DEFAULT_PROFILE_FORM_VALUE;
  }
  try {
    const raw = window.localStorage.getItem(PROFILE_FORM_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_PROFILE_FORM_VALUE;
    }
    const parsed = JSON.parse(raw) as Partial<ProfileFormValue>;
    return { ...DEFAULT_PROFILE_FORM_VALUE, ...parsed };
  } catch {
    return DEFAULT_PROFILE_FORM_VALUE;
  }
}

export function saveProfileFormValue(value: ProfileFormValue): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(PROFILE_FORM_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Non-secret UX convenience state only -- a full disk or disabled
    // storage should never break the app, just skip persistence silently.
  }
}
