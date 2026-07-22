/**
 * Composes the public share URL for a plan share id.
 *
 * Unlike the Streamlit app's `frontend/components/share_button.py`
 * (`compose_share_url` + `MACROCHEF_PUBLIC_URL`), this SPA is always served
 * BY the same FastAPI process as the API (`app/spa.py`), in every
 * environment -- there is no separate "public base URL" setting to plumb
 * through. `origin` is expected to be `window.location.origin` at the call
 * site; this function itself makes no `window` reference so it stays
 * trivially unit-testable.
 */
export function composeShareUrl(origin: string, shareId: string): string {
  const base = origin.replace(/\/+$/, "");
  return `${base}/shared/${encodeURIComponent(shareId)}`;
}
