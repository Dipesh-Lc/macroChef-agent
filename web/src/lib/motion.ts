/**
 * Micro-interaction constants + the runtime `prefers-reduced-motion` check
 * for the JS-driven animation this step adds (`useCountUp`). CSS-driven
 * transitions/animations are already globally neutralized by the
 * `@media (prefers-reduced-motion: reduce)` block in `index.css` (zeroes
 * `transition-duration`/`animation-duration` everywhere); a
 * `requestAnimationFrame` loop has no such CSS property to zero out, so it
 * needs its own check. Guarded for test/SSR environments where
 * `window.matchMedia` may not exist -- jsdom does not implement it.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Shared micro-interaction duration, 150-200ms per ROADMAP Step 4.5 --
 * single source so hover/expand/count-up agree without hand-tuning each
 * call site separately. */
export const MICRO_INTERACTION_MS = 180;
