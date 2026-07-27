import { describe, expect, it } from "vitest";
import type { RecipeCandidate, SaveRecipeCandidatesResponse } from "../api/types";
import { preselectedCandidateIds, summarizeSaveOutcome } from "./libraryCandidates";

function buildCandidate(id: string): RecipeCandidate {
  return {
    candidate_id: id,
    title: `Candidate ${id}`,
    ingredients: [],
    instructions: [],
    servings: 1,
    source_type: "mock",
    home_cookable_score: 1,
    derived_allergens: [],
  };
}

describe("preselectedCandidateIds", () => {
  it("pre-checks exactly the first 3 candidates in list order", () => {
    const candidates = ["a", "b", "c", "d", "e"].map(buildCandidate);
    const selected = preselectedCandidateIds(candidates);
    expect(selected).toEqual(new Set(["a", "b", "c"]));
  });

  it("does not fabricate a 4th selection when fewer than 3 candidates exist", () => {
    const candidates = ["a", "b"].map(buildCandidate);
    expect(preselectedCandidateIds(candidates)).toEqual(new Set(["a", "b"]));
  });

  it("returns an empty set for no candidates", () => {
    expect(preselectedCandidateIds([])).toEqual(new Set());
  });

  it("supports a custom preselect count", () => {
    const candidates = ["a", "b", "c", "d"].map(buildCandidate);
    expect(preselectedCandidateIds(candidates, 1)).toEqual(new Set(["a"]));
  });
});

describe("summarizeSaveOutcome", () => {
  function buildResponse(
    overrides: Partial<SaveRecipeCandidatesResponse>,
  ): SaveRecipeCandidatesResponse {
    return {
      saved_recipe_ids: [],
      skipped_duplicates: [],
      failed_candidates: [],
      debug_trace: [],
      ...overrides,
    };
  }

  it("counts saved, skipped-duplicate, and failed candidates separately", () => {
    const response = buildResponse({
      saved_recipe_ids: ["r1", "r2"],
      skipped_duplicates: ["r3"],
      failed_candidates: [{ candidate_id: "r4", reason: "invalid" }],
    });
    expect(summarizeSaveOutcome(response)).toEqual({
      savedCount: 2,
      skippedDuplicateCount: 1,
      failedCount: 1,
    });
  });

  it("treats missing arrays as zero counts", () => {
    expect(summarizeSaveOutcome({})).toEqual({
      savedCount: 0,
      skippedDuplicateCount: 0,
      failedCount: 0,
    });
  });
});
