import { useId } from "react";
import { MACRO_COLOR_VAR, MACRO_LABEL, MACRO_ORDER, buildMacroSegments, sortByMacroOrder, type MacroSegmentInput } from "../lib/macroChart";

const BAR_WIDTH = 10;
const BAR_GAP = 3;

export interface MacroTrendDay {
  /** e.g. "Day 1" -- rendered under the bar group and read out in the SVG's `aria-label`. */
  label: string;
  segments: MacroSegmentInput[];
}

export interface MacroTrendBarsProps {
  days: MacroTrendDay[];
  /** Chart area height in px, fixed regardless of data -- see
   * `MacroRadial`'s `size` prop docstring for why this stays a fixed
   * dimension rather than one derived from content. */
  chartHeight?: number;
}

/**
 * Hand-rolled SVG grouped-bar macro-progress-vs-target trend across
 * multiple days (the week page's per-day counterpart to `MacroRadial`'s
 * single-day rings) -- one protein/carbs/fat bar triplet per day, each
 * bar's fill height equal to that macro's clamped fraction of its own
 * target, colored per the design system's basil/honey/chili mapping.
 *
 * Same solid-vs-hatched and `verified`-provenance contract as
 * `MacroRadial.tsx` (see that component's docstring in full) -- every
 * current Week page call site passes `verified: true` for the same reason:
 * `WeeklyPlan.days` (a list of `DayPlan`) carries no per-macro
 * grounding-trust field.
 */
export function MacroTrendBars({ days, chartHeight = 96 }: MacroTrendBarsProps) {
  const patternIdBase = useId();
  const groupWidth = MACRO_ORDER.length * BAR_WIDTH + (MACRO_ORDER.length - 1) * BAR_GAP;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end gap-4 overflow-x-auto pb-1">
        {days.map((day, dayIndex) => {
          const segments = buildMacroSegments(sortByMacroOrder(day.segments));
          const summary = segments
            .map((segment) => `${MACRO_LABEL[segment.macro]} ${segment.percent}%${segment.verified ? "" : " (estimated)"}`)
            .join(", ");

          return (
            <div key={`${day.label}-${dayIndex}`} className="flex shrink-0 flex-col items-center gap-1.5">
              <svg
                width={groupWidth}
                height={chartHeight}
                viewBox={`0 0 ${groupWidth} ${chartHeight}`}
                role="img"
                aria-label={`${day.label}: ${summary}`}
              >
                <defs>
                  {segments.map((segment) => (
                    <pattern
                      key={segment.macro}
                      id={`${patternIdBase}-${dayIndex}-${segment.macro}`}
                      patternUnits="userSpaceOnUse"
                      width={5}
                      height={5}
                      patternTransform="rotate(45)"
                    >
                      <rect width={5} height={5} style={{ fill: MACRO_COLOR_VAR[segment.macro], opacity: 0.25 }} />
                      <line x1={0} y1={0} x2={0} y2={5} style={{ stroke: MACRO_COLOR_VAR[segment.macro], strokeWidth: 2.5 }} />
                    </pattern>
                  ))}
                </defs>
                {segments.map((segment, index) => {
                  const barHeight = Math.max(2, segment.clampedFraction * (chartHeight - 4));
                  const x = index * (BAR_WIDTH + BAR_GAP);
                  const y = chartHeight - barHeight;
                  const fill = segment.verified
                    ? MACRO_COLOR_VAR[segment.macro]
                    : `url(#${patternIdBase}-${dayIndex}-${segment.macro})`;
                  return (
                    <rect
                      key={segment.macro}
                      x={x}
                      y={y}
                      width={BAR_WIDTH}
                      height={barHeight}
                      rx={2}
                      style={{ fill, transition: "height 200ms ease-out, y 200ms ease-out" }}
                    />
                  );
                })}
                <rect x={0} y={chartHeight - 1} width={groupWidth} height={1} style={{ fill: "var(--color-sage-line)" }} />
              </svg>
              <span className="font-mono text-[0.65rem] text-cast-iron/60">{day.label}</span>
            </div>
          );
        })}
      </div>

      <ul className="flex flex-wrap gap-3 text-[0.65rem] text-cast-iron/60">
        {MACRO_ORDER.map((macro) => (
          <li key={macro} className="flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: MACRO_COLOR_VAR[macro] }}
            />
            {MACRO_LABEL[macro]}
          </li>
        ))}
      </ul>
    </div>
  );
}
