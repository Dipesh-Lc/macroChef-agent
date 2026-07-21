import type { MacroDisplayState } from "../lib/macroDisplay";

/**
 * The signature visual element of the "honest kitchen ledger" identity:
 * verified (USDA-grounded) vs unverified data render with distinct visual
 * grammar everywhere. Driven ENTIRELY by `macroDisplayState` -- never makes
 * its own trust decision.
 */
export function TrustBadge({ state }: { state: MacroDisplayState }) {
  if (state === "grounded") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-basil px-2 py-0.5 font-mono text-xs font-medium text-basil">
        USDA ✓
      </span>
    );
  }

  if (state === "partial") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-honey-dark bg-honey/10 px-2 py-0.5 font-mono text-xs font-medium text-honey-dark">
        ~ partial
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-sage-line px-2 py-0.5 font-mono text-xs font-medium text-cast-iron/50">
      unverified
    </span>
  );
}
