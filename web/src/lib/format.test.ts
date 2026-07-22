import { describe, expect, it } from "vitest";
import { formatGrams, formatKcal, formatPercent, formatRelativeError } from "./format";

describe("format helpers", () => {
  it("formatKcal rounds to the nearest whole kcal", () => {
    expect(formatKcal(499.6)).toBe("500 kcal");
    expect(formatKcal(0)).toBe("0 kcal");
  });

  it("formatGrams rounds to the nearest whole gram", () => {
    expect(formatGrams(39.5)).toBe("40g");
  });

  it("formatPercent converts a 0..1 fraction to a whole-number percent", () => {
    expect(formatPercent(0.5)).toBe("50%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(0.333, 1)).toBe("33.3%");
  });

  it("formatRelativeError signs the deviation from target", () => {
    expect(formatRelativeError(120, 100)).toBe("+20%");
    expect(formatRelativeError(80, 100)).toBe("-20%");
    expect(formatRelativeError(100, 100)).toBe("0%");
    expect(formatRelativeError(0, 0)).toBe("0%");
  });
});
