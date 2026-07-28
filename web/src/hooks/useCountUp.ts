import { useEffect, useRef, useState } from "react";
import { MICRO_INTERACTION_MS, prefersReducedMotion } from "../lib/motion";

/**
 * Animates a displayed number up from 0 to `target` (ease-out cubic) over
 * `durationMs` -- the "count-up animation on macro totals after results
 * land" task in ROADMAP Step 4.5. Starts at 0 rather than `target` so the
 * FIRST mount (exactly the moment a plan/recipe result lands and this
 * component mounts) always animates; a later re-render with a changed
 * `target` animates from whatever the hook last settled on, which reads as
 * an update, not a fresh count-up -- both are intentional.
 *
 * Respects `prefers-reduced-motion` (checked via `window.matchMedia`, since
 * a `requestAnimationFrame` loop isn't covered by `index.css`'s
 * transition/animation-duration reset -- see `lib/motion.ts`): when reduced
 * motion is requested, or in a non-browser environment without
 * `requestAnimationFrame` (e.g. some test setups), `value` tracks `target`
 * directly with no intermediate frames, and no rAF loop ever starts.
 */
export function useCountUp(target: number, durationMs: number = MICRO_INTERACTION_MS * 2): number {
  const reduced = prefersReducedMotion() || typeof requestAnimationFrame !== "function";
  const [value, setValue] = useState(reduced ? target : 0);
  // Tracks the last `target` this hook has seen, purely to detect a change
  // during render -- see the reduced-motion block below.
  const [prevTarget, setPrevTarget] = useState(target);
  const frameRef = useRef<number | null>(null);
  // Mirrors `value` (kept current via the effect below) so the rAF effect
  // always reads the true latest displayed value as its animation start
  // point, including mid-animation retargeting.
  const valueRef = useRef(value);

  // Reduced-motion / no-rAF path: adjust state during render when `target`
  // changes, rather than via a `useEffect` -- React's documented
  // "adjusting state when a prop changes" pattern
  // (https://react.dev/learn/you-might-not-need-an-effect). This keeps a
  // synchronous `setState` call OUT of a `useEffect` body (which
  // `react-hooks/set-state-in-effect` flags as a cascading-render risk).
  // Comparing against tracked state (not a ref -- `react-hooks/refs`
  // forbids reading/writing refs during render) so it only fires on an
  // actual `target` change and converges in the single extra render
  // React's docs describe, never loops.
  if (reduced && target !== prevTarget) {
    setPrevTarget(target);
    setValue(target);
  }

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  useEffect(() => {
    if (reduced) {
      return;
    }

    const startValue = valueRef.current;
    const delta = target - startValue;
    if (delta === 0) {
      return;
    }
    const startedAt =
      typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();

    function tick(now: number) {
      const elapsed = now - startedAt;
      const progress = Math.min(1, durationMs <= 0 ? 1 : elapsed / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = startValue + delta * eased;
      valueRef.current = next;
      setValue(next);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current != null) {
        cancelAnimationFrame(frameRef.current);
      }
    };
    // Deliberately excludes `value` -- the loop reads it once via
    // `valueRef.current` as its start point; including it would restart the
    // loop on every intermediate frame update.
  }, [target, durationMs, reduced]);

  return value;
}
