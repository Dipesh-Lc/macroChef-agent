/** Small formatting helpers -- pure functions, no React, no API calls. */

export function formatKcal(value: number): string {
  return `${Math.round(value)} kcal`;
}

export function formatGrams(value: number): string {
  return `${Math.round(value)}g`;
}

/** `fraction` is 0..1 (e.g. RecipeNutrition.coverage) -> "62%". */
export function formatPercent(fraction: number, fractionDigits = 0): string {
  return `${(fraction * 100).toFixed(fractionDigits)}%`;
}

/** Signed relative error of `actual` vs `target`, e.g. "+12%" / "-8%" / "0%". */
export function relativeErrorPercent(actual: number, target: number): number {
  if (target === 0) {
    return actual === 0 ? 0 : Number.POSITIVE_INFINITY;
  }
  return ((actual - target) / target) * 100;
}

export function formatRelativeError(actual: number, target: number): string {
  const pct = relativeErrorPercent(actual, target);
  if (!Number.isFinite(pct)) {
    return "n/a";
  }
  const rounded = Math.round(pct);
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded}%`;
}
