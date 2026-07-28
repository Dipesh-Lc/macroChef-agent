import { describe, expect, it } from "vitest";
import {
  buildMacroSegments,
  clamp01,
  fractionOfTarget,
  sortByMacroOrder,
  toPercent,
  type MacroSegmentInput,
} from "./macroChart";

describe("clamp01", () => {
  it("passes through values already inside [0, 1]", () => {
    expect(clamp01(0)).toBe(0);
    expect(clamp01(1)).toBe(1);
    expect(clamp01(0.42)).toBe(0.42);
  });

  it("clamps below 0 up to 0", () => {
    expect(clamp01(-0.5)).toBe(0);
    expect(clamp01(-100)).toBe(0);
  });

  it("clamps above 1 down to 1", () => {
    expect(clamp01(1.5)).toBe(1);
    expect(clamp01(100)).toBe(1);
  });

  it("never leaks NaN or Infinity", () => {
    expect(clamp01(NaN)).toBe(0);
    expect(clamp01(Number.POSITIVE_INFINITY)).toBe(1);
    expect(clamp01(Number.NEGATIVE_INFINITY)).toBe(0);
  });
});

describe("fractionOfTarget", () => {
  it("divides actual by target when target is a positive number", () => {
    expect(fractionOfTarget(50, 100)).toBe(0.5);
    expect(fractionOfTarget(150, 100)).toBe(1.5);
    expect(fractionOfTarget(0, 100)).toBe(0);
  });

  it("returns null for a missing target -- never coerced to 0", () => {
    expect(fractionOfTarget(50, null)).toBeNull();
    expect(fractionOfTarget(50, undefined)).toBeNull();
  });

  it("returns null for a non-positive target (0 or negative)", () => {
    expect(fractionOfTarget(50, 0)).toBeNull();
    expect(fractionOfTarget(50, -10)).toBeNull();
  });
});

describe("toPercent", () => {
  it("rounds a 0..1 fraction to a 0..100 integer", () => {
    expect(toPercent(0)).toBe(0);
    expect(toPercent(1)).toBe(100);
    expect(toPercent(0.5)).toBe(50);
  });

  it("rounds .5-boundary fractions up, matching Math.round", () => {
    expect(toPercent(0.125)).toBe(13);
    expect(toPercent(0.004)).toBe(0);
  });

  it("clamps out-of-range fractions before rounding", () => {
    expect(toPercent(1.4)).toBe(100);
    expect(toPercent(-0.4)).toBe(0);
  });
});

describe("buildMacroSegments", () => {
  it("computes fraction/clampedFraction/percent for a normal in-range segment", () => {
    const [segment] = buildMacroSegments([{ macro: "protein", grams: 40, targetGrams: 80, verified: true }]);
    expect(segment.fractionOfTarget).toBe(0.5);
    expect(segment.clampedFraction).toBe(0.5);
    expect(segment.percent).toBe(50);
    expect(segment.overTarget).toBe(false);
  });

  it("clamps an over-target segment's drawn fraction to 1 while keeping the raw fraction unclamped", () => {
    const [segment] = buildMacroSegments([{ macro: "fat", grams: 60, targetGrams: 40, verified: true }]);
    expect(segment.fractionOfTarget).toBe(1.5);
    expect(segment.clampedFraction).toBe(1);
    expect(segment.percent).toBe(100);
    expect(segment.overTarget).toBe(true);
  });

  it("is not overTarget exactly at the target (boundary case)", () => {
    const [segment] = buildMacroSegments([{ macro: "carbs", grams: 100, targetGrams: 100, verified: true }]);
    expect(segment.fractionOfTarget).toBe(1);
    expect(segment.overTarget).toBe(false);
  });

  it("renders a null-target segment as clampedFraction 0 (empty ring/bar), not an error", () => {
    const [segment] = buildMacroSegments([{ macro: "carbs", grams: 75, targetGrams: null, verified: true }]);
    expect(segment.fractionOfTarget).toBeNull();
    expect(segment.clampedFraction).toBe(0);
    expect(segment.percent).toBe(0);
  });

  it("passes each segment's verified flag through independently -- the hatched-segment boundary", () => {
    const inputs: MacroSegmentInput[] = [
      { macro: "protein", grams: 40, targetGrams: 80, verified: true },
      { macro: "carbs", grams: 40, targetGrams: 80, verified: false },
      { macro: "fat", grams: 40, targetGrams: 80, verified: true },
    ];
    const segments = buildMacroSegments(inputs);
    expect(segments.map((s) => s.verified)).toEqual([true, false, true]);
    // Identical grams/target, differing only in verified -- everything else
    // about the carbs segment must match its protein/fat siblings.
    expect(segments[1].clampedFraction).toBe(segments[0].clampedFraction);
    expect(segments[1].percent).toBe(segments[0].percent);
  });

  it("preserves input order", () => {
    const segments = buildMacroSegments([
      { macro: "fat", grams: 1, targetGrams: 1, verified: true },
      { macro: "protein", grams: 1, targetGrams: 1, verified: true },
      { macro: "carbs", grams: 1, targetGrams: 1, verified: true },
    ]);
    expect(segments.map((s) => s.macro)).toEqual(["fat", "protein", "carbs"]);
  });
});

describe("sortByMacroOrder", () => {
  it("reorders to protein, carbs, fat regardless of input order", () => {
    const sorted = sortByMacroOrder([
      { macro: "fat" as const, value: "f" },
      { macro: "protein" as const, value: "p" },
      { macro: "carbs" as const, value: "c" },
    ]);
    expect(sorted.map((item) => item.macro)).toEqual(["protein", "carbs", "fat"]);
  });

  it("does not mutate the input array", () => {
    const input = [{ macro: "fat" as const }, { macro: "protein" as const }];
    const sorted = sortByMacroOrder(input);
    expect(sorted).not.toBe(input);
    expect(input.map((item) => item.macro)).toEqual(["fat", "protein"]);
  });
});
