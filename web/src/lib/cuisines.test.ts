import { describe, expect, it } from "vitest";
import { CUISINE_OPTIONS } from "./cuisines";

// Old, independent, mismatched lists this canonical list replaces --
// `PantryInput.tsx`'s single-select `<select>` list (minus "Any", which
// stays local to that component) and `lib/discoverForm.ts`'s multi-select
// pill list. Every cuisine that used to be selectable in either place must
// still be selectable via the canonical list -- no regressions.
const OLD_PANTRY_INPUT_CUISINES = [
  "Mediterranean",
  "Mexican",
  "Italian",
  "Indian",
  "Japanese",
  "American",
  "Thai",
];

const OLD_DISCOVER_FORM_CUISINES = [
  "Italian",
  "Indian",
  "Japanese",
  "Chinese",
  "Mexican",
  "Mediterranean",
  "American",
];

describe("CUISINE_OPTIONS canonical list", () => {
  it("is non-empty", () => {
    expect(CUISINE_OPTIONS.length).toBeGreaterThan(0);
  });

  it("has no duplicates", () => {
    expect(new Set(CUISINE_OPTIONS).size).toBe(CUISINE_OPTIONS.length);
  });

  it("is alphabetically sorted", () => {
    const sorted = [...CUISINE_OPTIONS].sort((a, b) => a.localeCompare(b));
    expect([...CUISINE_OPTIONS]).toEqual(sorted);
  });

  it("is a superset of PantryInput's old cuisine list (no regressions)", () => {
    for (const cuisine of OLD_PANTRY_INPUT_CUISINES) {
      expect(CUISINE_OPTIONS).toContain(cuisine);
    }
  });

  it("is a superset of discoverForm's old cuisine list (no regressions)", () => {
    for (const cuisine of OLD_DISCOVER_FORM_CUISINES) {
      expect(CUISINE_OPTIONS).toContain(cuisine);
    }
  });
});
