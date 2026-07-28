/**
 * Pure chart math for `MacroRadial`/`MacroTrendBars` (ROADMAP Step 4.5) --
 * percent-of-target calculation, [0,1] clamping, and the verified/estimated
 * segment split. No React, no DOM, no network -- this is the only part of
 * the chart pipeline the roadmap step's Tests bullet asks for ("unit tests
 * for chart math ... not full render/snapshot tests").
 *
 * PROVENANCE NOTE (read before wiring a new caller): `verified` is an
 * OPAQUE INPUT the caller supplies -- this module never invents or infers
 * it from anything. The only place in this codebase with a real,
 * non-fabricated per-macro grounding-trust signal today is a single
 * recipe's `macroDisplayState` (`./macroDisplay.ts`); neither `DayPlan` nor
 * `WeeklyPlan` carries any such field (see `app/schemas/day_plan.py` /
 * `weekly_plan.py` -- both only report summed grams, never a trust flag per
 * macro), so every current Day/Week page caller passes `verified: true` for
 * all three rings/bars. See `MacroRadial.tsx`'s own docstring for the full
 * reasoning and the ROADMAP 4.5 executor report's ASSUMPTIONS section.
 */

export type MacroKey = "protein" | "carbs" | "fat";

/** basil = protein, honey = carbs, chili = fat -- the design system's fixed
 * macro color mapping (ROADMAP Step 4.5); never remapped per-caller. */
export const MACRO_ORDER: MacroKey[] = ["protein", "carbs", "fat"];

export const MACRO_LABEL: Record<MacroKey, string> = {
  protein: "Protein",
  carbs: "Carbs",
  fat: "Fat",
};

export const MACRO_COLOR_VAR: Record<MacroKey, string> = {
  protein: "var(--color-basil)",
  carbs: "var(--color-honey)",
  fat: "var(--color-chili)",
};

/**
 * Clamps to [0, 1]. Non-finite input (NaN from a 0/0, +/-Infinity) never
 * leaks out as NaN/Infinity -- NaN and -Infinity clamp to 0, +Infinity
 * clamps to 1 -- so a caller can feed this straight into an SVG
 * `stroke-dashoffset`/bar-height fraction without a separate guard.
 */
export function clamp01(value: number): number {
  if (Number.isNaN(value)) {
    return 0;
  }
  if (!Number.isFinite(value)) {
    return value > 0 ? 1 : 0;
  }
  return Math.min(1, Math.max(0, value));
}

/**
 * `actual / target`, or `null` when there is no meaningful target to
 * measure against. A target of `null`/`undefined`/`<= 0` is "no target",
 * never coerced to "0% of target" -- mirrors `PlanMacroSummary`'s existing
 * `target != null` gate for the same reason (a missing target is a
 * different UI state than a met-at-zero one).
 */
export function fractionOfTarget(actual: number, target: number | null | undefined): number | null {
  if (target == null || target <= 0) {
    return null;
  }
  return actual / target;
}

/** `fraction` (already 0..1, e.g. a `clampedFraction`) -> a rounded 0..100 integer. */
export function toPercent(fraction: number): number {
  return Math.round(clamp01(fraction) * 100);
}

export interface MacroSegmentInput {
  macro: MacroKey;
  grams: number;
  targetGrams?: number | null;
  /** Whether this segment's `grams` is USDA-grounded (solid) or an
   * estimate/unverified figure (hatched). Always caller-supplied -- see
   * this module's docstring; never computed here. */
  verified: boolean;
}

export interface MacroSegment {
  macro: MacroKey;
  grams: number;
  targetGrams: number | null;
  /** Raw fraction of target, unclamped -- can exceed 1 (over target) or be `null` (no target). */
  fractionOfTarget: number | null;
  /** `fractionOfTarget` clamped to [0, 1] -- what a ring/bar actually draws. */
  clampedFraction: number;
  /** `true` iff the raw fraction exceeds 1 -- callers may render an overflow marker. */
  overTarget: boolean;
  /** `clampedFraction` as a rounded 0..100 integer, for mono-numeral labels. */
  percent: number;
  verified: boolean;
}

/**
 * Builds the fully-derived segment list a chart component renders from,
 * preserving input order. Each input's `verified` flag passes straight
 * through untouched -- this is the "hatched-segment-by-verified-flag"
 * boundary the roadmap step's Tests bullet calls out: two segments with
 * identical grams/target but different `verified` values must diverge only
 * in `.verified`, nothing else.
 */
export function buildMacroSegments(inputs: MacroSegmentInput[]): MacroSegment[] {
  return inputs.map((input) => {
    const fraction = fractionOfTarget(input.grams, input.targetGrams);
    const clamped = fraction == null ? 0 : clamp01(fraction);
    return {
      macro: input.macro,
      grams: input.grams,
      targetGrams: input.targetGrams ?? null,
      fractionOfTarget: fraction,
      clampedFraction: clamped,
      overTarget: fraction != null && fraction > 1,
      percent: toPercent(clamped),
      verified: input.verified,
    };
  });
}

/** Sorts (a copy of) `inputs`/segments into the fixed protein/carbs/fat
 * display order, regardless of the order a caller supplied them in -- so
 * `MacroRadial`'s ring nesting and `MacroTrendBars`' bar grouping are
 * always consistent. */
export function sortByMacroOrder<T extends { macro: MacroKey }>(items: T[]): T[] {
  return [...items].sort((a, b) => MACRO_ORDER.indexOf(a.macro) - MACRO_ORDER.indexOf(b.macro));
}
