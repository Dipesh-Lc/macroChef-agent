import { useId } from "react";
import { useCountUp } from "../hooks/useCountUp";
import {
  MACRO_COLOR_VAR,
  MACRO_LABEL,
  buildMacroSegments,
  sortByMacroOrder,
  type MacroSegment,
  type MacroSegmentInput,
} from "../lib/macroChart";

const STROKE_WIDTH = 8;
const RING_GAP = 10;

export interface MacroRadialProps {
  /** Protein/carbs/fat inputs, any order -- sorted to the fixed protein
   * (outer ring) -> carbs -> fat (inner ring) order before rendering. */
  segments: MacroSegmentInput[];
  /** Square SVG size in px. Fixed (never derived from content), so this
   * component never contributes to a results-swap-in layout shift -- see
   * the ROADMAP 4.5 executor report's acceptance-criteria note. */
  size?: number;
  /** Accessible label prefix, e.g. "Today's macros vs target". */
  title?: string;
}

/**
 * Hand-rolled SVG radial (concentric-ring) macro-progress-vs-target
 * visualization -- three rings (protein outer, carbs middle, fat inner)
 * filled to each macro's own clamped fraction-of-target, colored per the
 * design system's fixed mapping (basil/honey/chili). No new chart
 * dependency: ROADMAP Step 4.5 explicitly prefers hand-rolled SVG over
 * pulling in recharts for two charts.
 *
 * Solid vs hatched per ring follows `segments[].verified`: an SVG
 * `<pattern>` diagonal-hatch fill substitutes for the solid stroke color
 * when a segment is unverified.
 *
 * PROVENANCE (read before wiring a new caller): `verified` is NEVER
 * computed in this component -- see `lib/macroChart.ts`'s docstring. Every
 * current Day/Week page call site (`DayPlanPage`) passes `verified: true`
 * for all three rings because neither `DayPlan` nor `WeeklyPlan` carries a
 * per-macro grounding-trust field today (unlike a single `Recipe`, which
 * has one via `macroDisplayState`, `lib/macroDisplay.ts`). The hatch
 * machinery exists and is unit-tested (`lib/macroChart.test.ts`) so a
 * future caller with a real trust signal can use it without a rewrite --
 * flagged explicitly as a conservative, honest interpretation in the
 * ROADMAP 4.5 executor report's ASSUMPTIONS section, not a fabricated flag.
 */
export function MacroRadial({ segments: inputs, size = 148, title = "Macro progress" }: MacroRadialProps) {
  const patternIdBase = useId();
  const segments = buildMacroSegments(sortByMacroOrder(inputs));
  const center = size / 2;

  const summaryText = segments
    .map((segment) => `${MACRO_LABEL[segment.macro]} ${segment.percent}%${segment.targetGrams == null ? "" : " of target"}${segment.verified ? "" : " (estimated)"}`)
    .join(", ");

  return (
    <div className="flex flex-col items-center gap-3" style={{ width: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${title}: ${summaryText}`}>
        <defs>
          {segments.map((segment) => (
            <pattern
              key={segment.macro}
              id={`${patternIdBase}-${segment.macro}`}
              patternUnits="userSpaceOnUse"
              width={6}
              height={6}
              patternTransform="rotate(45)"
            >
              <rect width={6} height={6} style={{ fill: MACRO_COLOR_VAR[segment.macro], opacity: 0.25 }} />
              <line x1={0} y1={0} x2={0} y2={6} style={{ stroke: MACRO_COLOR_VAR[segment.macro], strokeWidth: 3 }} />
            </pattern>
          ))}
        </defs>
        {segments.map((segment, index) => {
          const radius = center - STROKE_WIDTH / 2 - index * RING_GAP;
          if (radius <= 0) {
            return null;
          }
          const circumference = 2 * Math.PI * radius;
          const dashoffset = circumference * (1 - segment.clampedFraction);
          const paint = segment.verified ? MACRO_COLOR_VAR[segment.macro] : `url(#${patternIdBase}-${segment.macro})`;
          return (
            <g key={segment.macro} transform={`rotate(-90 ${center} ${center})`}>
              <circle
                cx={center}
                cy={center}
                r={radius}
                fill="none"
                strokeWidth={STROKE_WIDTH}
                style={{ stroke: "var(--color-sage-line)" }}
              />
              <circle
                cx={center}
                cy={center}
                r={radius}
                fill="none"
                strokeWidth={STROKE_WIDTH}
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={dashoffset}
                style={{ stroke: paint, transition: "stroke-dashoffset 200ms ease-out" }}
              />
            </g>
          );
        })}
      </svg>

      <ul className="flex w-full flex-col gap-1">
        {segments.map((segment) => (
          <MacroRadialRow key={segment.macro} segment={segment} />
        ))}
      </ul>
    </div>
  );
}

function MacroRadialRow({ segment }: { segment: MacroSegment }) {
  const animatedGrams = useCountUp(Math.round(segment.grams));

  return (
    <li className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-1.5 text-cast-iron/70">
        <span
          aria-hidden="true"
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: MACRO_COLOR_VAR[segment.macro] }}
        />
        {MACRO_LABEL[segment.macro]}
        {!segment.verified && (
          <span className="rounded-full border border-dashed border-sage-line px-1 text-[0.6rem] uppercase text-cast-iron/50">
            est.
          </span>
        )}
      </span>
      <span className="font-mono text-cast-iron">
        {Math.round(animatedGrams)}g
        {segment.targetGrams != null && (
          <span className="text-cast-iron/50"> / {Math.round(segment.targetGrams)}g</span>
        )}
      </span>
    </li>
  );
}
