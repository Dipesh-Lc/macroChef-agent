/**
 * Pure helpers for the recipe-discovery candidate list, ported from
 * `frontend/components/recipe_candidate_cards.py`'s
 * `render_recipe_candidate_cards` (pre-check rule) and
 * `frontend/pages/1_Recipe_Library_Builder.py`'s save-response handling
 * (outcome summary). SOURCE OF TRUTH for the pre-check rule is the Python
 * component: `value=index <= 3` over a 1-based `enumerate(candidates,
 * start=1)`, i.e. the first three candidates in API response order --
 * never a "top 3 by some score" rule, since candidates carry no score.
 */
import type { RecipeCandidate, SaveRecipeCandidatesResponse } from "../api/types";

const DEFAULT_PRESELECT_COUNT = 3;

/** IDs of the candidates that should start checked -- the first N (default
 * 3) in list order, matching the Streamlit `index <= 3` rule exactly. */
export function preselectedCandidateIds(
  candidates: RecipeCandidate[],
  preselectCount: number = DEFAULT_PRESELECT_COUNT,
): Set<string> {
  return new Set(candidates.slice(0, preselectCount).map((candidate) => candidate.candidate_id));
}

export interface SaveOutcomeSummary {
  savedCount: number;
  skippedDuplicateCount: number;
  failedCount: number;
}

/** Classifies a `/library/save` response into the three distinct outcomes
 * the Streamlit page reported separately (`st.success` / `st.warning` /
 * `st.error`) rather than a single collapsed "saved" message -- callers
 * render each count that is non-zero. */
export function summarizeSaveOutcome(response: SaveRecipeCandidatesResponse): SaveOutcomeSummary {
  return {
    savedCount: response.saved_recipe_ids?.length ?? 0,
    skippedDuplicateCount: response.skipped_duplicates?.length ?? 0,
    failedCount: response.failed_candidates?.length ?? 0,
  };
}
