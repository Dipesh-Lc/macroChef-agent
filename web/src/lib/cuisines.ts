/**
 * Canonical, alphabetically-sorted list of world cuisines. `cuisine` is a
 * free-text `string | null` everywhere in the backend (no enum in `app/` --
 * see `app/schemas/user.py` / `app/schemas/library.py`), so this frontend
 * list is the single source of truth for the UI. Previously `PantryInput.tsx`
 * and `lib/discoverForm.ts` each hardcoded their own short, mismatched
 * lists; both now import this instead.
 */
export const CUISINE_OPTIONS = [
  "American",
  "British",
  "Caribbean",
  "Chinese",
  "Ethiopian",
  "French",
  "German",
  "Greek",
  "Indian",
  "Indonesian",
  "Italian",
  "Japanese",
  "Korean",
  "Lebanese",
  "Mediterranean",
  "Mexican",
  "Middle Eastern",
  "Moroccan",
  "Nepali",
  "Persian",
  "Peruvian",
  "Portuguese",
  "Spanish",
  "Thai",
  "Turkish",
  "Vietnamese",
] as const;

export type CuisineOption = (typeof CUISINE_OPTIONS)[number];
