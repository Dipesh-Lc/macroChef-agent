import { useState } from "react";
import { ApiError, RateLimitError } from "../api/client";
import { createShare } from "../api/endpoints";
import type {
  BatchPlan,
  DayPlan,
  Recipe,
  ShareCreateRequest,
  ShoppingItem,
  WeeklyPlan,
} from "../api/types";
import { composeShareUrl } from "../lib/shareUrl";

/**
 * Generic share button for any of the five `POST /share` payload shapes
 * (roadmap item "Shareable plan URLs", Phase 4 item 4, extended by task
 * "Shareable Shopping Lists" to add the `shopping_list` plan type).
 * Forwards whichever already-assembled object the caller holds -- it makes
 * NO safety or field-selection decision itself; the server-side allowlist in
 * `app.services.share_service` is the sole authority on what actually gets
 * persisted/exposed (see that module's docstring), exactly like the
 * Streamlit precursor this ports (`frontend/components/share_button.py`).
 */
export type ShareButtonProps =
  | { planType: "recipe"; payload: Recipe }
  | { planType: "day"; payload: DayPlan }
  | { planType: "batch"; payload: BatchPlan }
  | { planType: "week"; payload: WeeklyPlan }
  | { planType: "shopping_list"; payload: ShoppingItem[] };

// Discriminated switch (not a computed-property object literal) so
// TypeScript keeps `payload`'s type correlated with `planType` -- see the
// `ShareButtonProps` union above.
function buildShareCreateRequest(props: ShareButtonProps): ShareCreateRequest {
  switch (props.planType) {
    case "recipe":
      return { plan_type: "recipe", recipe: props.payload };
    case "day":
      return { plan_type: "day", day_plan: props.payload };
    case "batch":
      return { plan_type: "batch", batch_plan: props.payload };
    case "week":
      return { plan_type: "week", weekly_plan: props.payload };
    case "shopping_list":
      return { plan_type: "shopping_list", shopping_list: props.payload };
  }
}

const COPIED_RESET_MS = 2000;

export function ShareButton(props: ShareButtonProps) {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleShare() {
    setPending(true);
    setError(null);
    try {
      const response = await createShare(buildShareCreateRequest(props));
      setShareUrl(composeShareUrl(window.location.origin, response.share_id));
    } catch (err) {
      if (err instanceof RateLimitError) {
        setError(err.message);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Could not create a share link. Please try again.");
      }
    } finally {
      setPending(false);
    }
  }

  async function handleCopy() {
    if (!shareUrl) {
      return;
    }
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), COPIED_RESET_MS);
    } catch {
      setError("Could not copy the link automatically -- select and copy it manually.");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {!shareUrl && (
        <button
          type="button"
          onClick={handleShare}
          disabled={pending}
          className="w-fit rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium text-cast-iron hover:bg-sage-line/40 disabled:opacity-50"
        >
          {pending ? "Creating share link…" : "Share"}
        </button>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
          <span>{error}</span>
          {!shareUrl && (
            <button
              type="button"
              onClick={handleShare}
              disabled={pending}
              className="shrink-0 underline underline-offset-2 disabled:opacity-50"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {shareUrl && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            readOnly
            value={shareUrl}
            aria-label="Share link"
            onFocus={(event) => event.currentTarget.select()}
            className="flex-1 rounded-md border border-sage-line bg-white px-2 py-1.5 font-mono text-xs text-cast-iron"
          />
          <button
            type="button"
            onClick={handleCopy}
            className="shrink-0 rounded-md border border-sage-line px-3 py-1.5 text-sm font-medium hover:bg-sage-line/40"
          >
            {copied ? "Copied" : "Copy link"}
          </button>
        </div>
      )}
    </div>
  );
}
