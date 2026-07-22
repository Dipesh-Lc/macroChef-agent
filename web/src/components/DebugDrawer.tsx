import { useState } from "react";
import type { RecommendationResponse } from "../api/types";

/**
 * Collapsible drawer at the bottom of the results column -- port of
 * `frontend/components/debug_panel.py`'s "System trace" tab content
 * (errors, `debug_trace`, raw response JSON). Plain-text rendering only:
 * everything here is inside a `<pre>` or plain JSX text, never
 * `dangerouslySetInnerHTML` (enforced repo-wide by `react/no-danger`).
 * `rejected_recipes` is deliberately NOT duplicated here -- it already has
 * its own always-visible treatment in `SafetyAuditPanel`.
 */
export function DebugDrawer({ response }: { response: RecommendationResponse | null }) {
  const [expanded, setExpanded] = useState(false);
  const [rawExpanded, setRawExpanded] = useState(false);

  if (!response) {
    return (
      <p className="text-xs text-cast-iron/50">
        Run the meal planner to see graph steps, rejected recipes, and raw output.
      </p>
    );
  }

  const errors = response.errors ?? [];
  const trace = response.debug_trace ?? [];

  return (
    <section className="rounded-lg border border-dashed border-sage-line bg-white">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="font-mono text-xs font-semibold uppercase tracking-widest text-cast-iron/60">
          Debug
        </span>
        <span className="text-xs text-cast-iron/50">{expanded ? "Hide" : "Show"}</span>
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 border-t border-dashed border-sage-line px-4 py-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">Errors</p>
            {errors.length === 0 ? (
              <p className="text-sm text-cast-iron/60">No errors.</p>
            ) : (
              <ul className="mt-1 list-inside list-disc text-sm text-chili">
                {errors.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-cast-iron/50">Graph trace</p>
            <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-cast-iron/5 p-2 font-mono text-xs text-cast-iron">
              {trace.length > 0 ? trace.join("\n") : "No trace recorded."}
            </pre>
          </div>

          <div>
            <button
              type="button"
              onClick={() => setRawExpanded((value) => !value)}
              className="text-xs font-medium uppercase tracking-wide text-cast-iron/60 underline underline-offset-2"
            >
              {rawExpanded ? "Hide raw JSON" : "Show raw JSON"}
            </button>
            {rawExpanded && (
              <pre className="mt-1 max-h-96 overflow-auto rounded-md bg-cast-iron/5 p-2 font-mono text-xs text-cast-iron">
                {JSON.stringify(response, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
