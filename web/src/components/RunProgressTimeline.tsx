import { useMemo } from "react";
import type { NodeRunEvent } from "../lib/sse";

/**
 * Live progress view for a `POST /recipes/recommend/stream` run (ROADMAP.md
 * Step 4.2). Replaces the old frozen "Finding recipes…" button state: a
 * vertical timeline fills in one row per graph node as its `RunEvent`s
 * arrive, so the 20-45s wait shows the system actually reasoning instead of
 * a static spinner. This component only *renders* what the deterministic
 * safety filter already decided (see `SafetyAuditPanel`'s docstring for the
 * same invariant) -- it never itself decides whether a recipe was safe, it
 * just reads `safety_filter_node`'s own summary sentence.
 *
 * Deliberately does NOT render the terminal `result` event's recommendations
 * -- `HomePage` already owns that rendering (RecipeCard list, SafetyAuditPanel,
 * ShoppingList, ...) and swaps this component out for it once a result
 * lands, rather than this component reimplementing/duplicating that view.
 */

const NODE_LABEL_OVERRIDES: Record<string, string> = {
  // A handful of node names don't humanize cleanly from their snake_case
  // form alone (e.g. "usda" would title-case to "Usda") -- everything else
  // falls through to `humanizeNodeName`'s generic split/capitalize.
  usda_grounding_node: "USDA nutrition grounding",
};

function humanizeNodeName(node: string): string {
  if (NODE_LABEL_OVERRIDES[node]) {
    return NODE_LABEL_OVERRIDES[node];
  }
  return node
    .replace(/_node$/, "")
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * `safety_filter_node`'s `finished` summary is always the literal sentence
 * "safety_filter_node: {valid} valid, {rejected} total rejected." (see
 * `app/graph/nodes.py::safety_filter_node`) -- never LLM-authored copy, so
 * matching its exact deterministic wording here is safe and stable. Only
 * flags the row when at least one recipe was actually rejected; "0 total
 * rejected" is good news, not a warning.
 */
function isSafetyRejectionRow(row: NodeRunEvent): boolean {
  if (row.node !== "safety_filter_node" || row.status !== "finished") {
    return false;
  }
  const match = row.summary.match(/(\d+)\s+total rejected/);
  return match !== null && Number(match[1]) > 0;
}

/** One row per node, keeping only the latest event seen for it (a node
 * typically emits `started` then `finished`/`failed` -- the timeline shows
 * the node "filling in" as that later event supersedes the row rather than
 * appending a second line for the same step), ordered by each node's first
 * appearance so the row order always matches the graph's actual run order. */
function latestEventPerNode(events: NodeRunEvent[]): NodeRunEvent[] {
  const order: string[] = [];
  const latest = new Map<string, NodeRunEvent>();
  for (const event of events) {
    if (!latest.has(event.node)) {
      order.push(event.node);
    }
    latest.set(event.node, event);
  }
  return order.map((node) => latest.get(node) as NodeRunEvent);
}

function StatusDot({ status }: { status: NodeRunEvent["status"] }) {
  if (status === "started") {
    // `animate-pulse` is neutralized under `prefers-reduced-motion` by the
    // global CSS reset in `index.css` (zeroes `animation-duration`
    // everywhere) -- same convention `HomePage`'s existing loading skeleton
    // already relies on, so no extra reduced-motion branching is needed here.
    return (
      <span
        aria-hidden="true"
        className="mt-1 h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-honey"
      />
    );
  }
  if (status === "failed") {
    return <span aria-hidden="true" className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-chili" />;
  }
  return <span aria-hidden="true" className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-basil" />;
}

function TimelineRow({ row }: { row: NodeRunEvent }) {
  const isRejection = isSafetyRejectionRow(row);
  const summaryClass =
    row.status === "failed" || isRejection ? "text-chili" : "text-cast-iron/70";

  return (
    <li className="flex items-start gap-3 border-b border-sage-line/60 py-2.5 last:border-none">
      <StatusDot status={row.status} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-cast-iron">{humanizeNodeName(row.node)}</span>
          {row.elapsed_ms !== null && (
            <span className="shrink-0 font-mono text-xs text-cast-iron/50">
              {Math.round(row.elapsed_ms)}ms
            </span>
          )}
        </div>
        <p data-rejection={isRejection || undefined} className={`text-sm ${summaryClass}`}>
          {row.summary}
        </p>
      </div>
    </li>
  );
}

export interface RunProgressTimelineProps {
  /** All `node` events received so far, in arrival order -- deduped to one
   * row per node internally (see `latestEventPerNode`). */
  events: NodeRunEvent[];
  /** "streaming" while the run is still in flight (shows shimmering
   * skeleton cards below the timeline); "error" once a terminal `error`
   * event (or a transport-level failure) ended the run. */
  phase: "streaming" | "error";
  /** User-facing message for the `error` phase -- the raw exception detail
   * from a mid-graph failure (`app.api.routes_stream`'s `error` event) or a
   * transport-level failure message; never displayed for its own sake, this
   * is deliberately generic per that endpoint's own contract. */
  errorDetail?: string | null;
  /** Retry affordance shown alongside the error message; omitted entirely
   * (no button rendered) if the caller has no retry to offer. */
  onRetry?: () => void;
}

export function RunProgressTimeline({ events, phase, errorDetail, onRetry }: RunProgressTimelineProps) {
  const rows = useMemo(() => latestEventPerNode(events), [events]);

  return (
    // `aria-live="polite"` so screen readers announce each row as it fills
    // in, rather than staying silent through the whole 20-45s run.
    <div className="flex flex-col gap-4" aria-live="polite">
      <ol className="flex flex-col rounded-lg border border-sage-line bg-white px-4">
        {rows.length === 0 ? (
          <li className="py-3 text-sm text-cast-iron/60">Starting…</li>
        ) : (
          rows.map((row) => <TimelineRow key={row.node} row={row} />)
        )}
      </ol>

      {phase === "streaming" && (
        <div className="flex flex-col gap-3" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              className="h-24 animate-pulse rounded-lg border border-dashed border-sage-line bg-white"
            />
          ))}
        </div>
      )}

      {phase === "error" && (
        <div className="flex flex-col gap-3 rounded-md border border-chili bg-chili/5 px-3 py-3 text-sm text-chili">
          <p>{errorDetail ?? "Something went wrong while finding recipes. Please try again."}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="w-fit rounded-md border border-chili px-3 py-1.5 text-xs font-semibold text-chili hover:bg-chili/10"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
