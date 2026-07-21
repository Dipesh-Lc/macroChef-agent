import { useState } from "react";
import { parseBoldSegments } from "../lib/parseBold";

// Verbatim, word-for-word port of the disclaimer in
// `frontend/streamlit_app.py` (the `st.warning(...)` call right after
// `render_profile_sidebar()`). It cites specific benchmark numbers --
// changing this wording is a human-gated act (CLAUDE.md "Honest scope");
// do not paraphrase, summarize, or "improve" it. The only change from the
// Streamlit source is markdown "**bold**" delimiters rendered as semantic
// <strong> (see ../lib/parseBold) instead of being interpreted by a
// markdown renderer -- the words themselves are unchanged.
const DISCLAIMER_TEXT =
  "**Hobby project — not medical advice.** MacroChef is an unpaid personal " +
  "project, not a certified nutrition or allergy-safety product. On its " +
  "259-case adversarial allergy benchmark, the deterministic judge flagged " +
  "16/259 recipes; written per-case adjudication found 0 true violations " +
  "(all 16 were judge false positives). " +
  "**If you have a food allergy, you must independently verify every " +
  "ingredient before you eat anything suggested here.**";

export function DisclaimerBanner() {
  const [expanded, setExpanded] = useState(false);
  const segments = parseBoldSegments(DISCLAIMER_TEXT);

  return (
    <div className="border-b border-sage-line bg-honey/15 px-4 py-2 text-sm text-cast-iron">
      <div className="mx-auto flex max-w-6xl items-start gap-3">
        <span aria-hidden="true" className="mt-0.5 text-honey-dark">
          ▲
        </span>
        <p className={expanded ? undefined : "line-clamp-2"}>
          {segments.map((segment, index) =>
            segment.bold ? (
              <strong key={index} className="font-semibold">
                {segment.text}
              </strong>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </p>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="ml-auto shrink-0 whitespace-nowrap text-xs font-medium text-basil underline underline-offset-2"
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      </div>
    </div>
  );
}
