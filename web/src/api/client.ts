/**
 * Thin `fetch` wrapper for talking to the MacroChef FastAPI backend.
 *
 * - Same-origin, relative URLs throughout: the dev proxy (`vite.config.ts`)
 *   forwards the backend prefixes to `localhost:8000`, and in production
 *   the built SPA is served BY the same FastAPI process (`app/spa.py`), so
 *   there is never a cross-origin request to worry about here.
 * - Session bootstrap: before the first SESSION-REQUIRED call, this module
 *   awaits a memoized (single-flight) `POST /session`. The browser stores
 *   the resulting HttpOnly `mc_session` cookie itself -- this code never
 *   reads or writes it directly.
 * - Every session-required call also sends `X-Requested-With: MacroChef`,
 *   the CSRF proof required by the cookie path of
 *   `app.dependencies.get_session_user` (see that module's docstring: a
 *   cross-site request cannot attach a custom header, so requiring one
 *   alongside the cookie is sufficient proof the request came from this
 *   app's own JS).
 * - On a 401 from a session-required call: mint a fresh session once, then
 *   retry the original request exactly once. A second 401 is surfaced as a
 *   real error -- no retry loop.
 */

const CSRF_HEADER_NAME = "X-Requested-With";
const CSRF_HEADER_VALUE = "MacroChef";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export class RateLimitError extends ApiError {
  constructor(detail?: unknown) {
    super(
      429,
      "You're sending requests too quickly — wait a moment and try again.",
      detail,
    );
    this.name = "RateLimitError";
  }
}

// Single-flight, memoized session-bootstrap promise. Reset to `null` only
// when a 401 forces a re-mint (see requestJson below) or when the mint
// itself fails, so a transient failure doesn't wedge every future call.
let sessionBootstrapPromise: Promise<void> | null = null;

async function mintSession(): Promise<void> {
  const response = await fetch("/session", { method: "POST" });
  if (!response.ok) {
    throw await toApiError(response);
  }
}

function bootstrapSession(): Promise<void> {
  if (!sessionBootstrapPromise) {
    sessionBootstrapPromise = mintSession().catch((error: unknown) => {
      sessionBootstrapPromise = null;
      throw error;
    });
  }
  return sessionBootstrapPromise;
}

function forceResessionBootstrap(): Promise<void> {
  sessionBootstrapPromise = null;
  return bootstrapSession();
}

async function extractDetail(response: Response): Promise<unknown> {
  try {
    const data: unknown = await response.clone().json();
    if (data && typeof data === "object" && "detail" in data) {
      return (data as { detail: unknown }).detail;
    }
    return data;
  } catch {
    try {
      return await response.clone().text();
    } catch {
      return undefined;
    }
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const detail = await extractDetail(response);
  if (response.status === 429) {
    return new RateLimitError(detail);
  }
  const message =
    typeof detail === "string" && detail.length > 0
      ? detail
      : `Request failed with status ${response.status}`;
  return new ApiError(response.status, message, detail);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-serialized as the request body (sets Content-Type: application/json). */
  json?: unknown;
  /** Pre-built body (e.g. FormData) sent as-is -- never combined with `json`. */
  body?: BodyInit;
  /** Whether this call requires an established session (bootstraps + sends the CSRF header). */
  sessionRequired?: boolean;
  signal?: AbortSignal;
  /** Optional request timeout, independent of any caller-supplied `signal`. */
  timeoutMs?: number;
}

function buildRequestInit(options: RequestOptions, signal: AbortSignal | undefined): RequestInit {
  const headers = new Headers();
  let body: BodyInit | undefined;

  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  } else if (options.body !== undefined) {
    body = options.body;
  }

  if (options.sessionRequired) {
    headers.set(CSRF_HEADER_NAME, CSRF_HEADER_VALUE);
  }

  return {
    method: options.method ?? "GET",
    headers,
    body,
    credentials: "same-origin",
    signal,
  };
}

/**
 * Perform an API call and parse its JSON response (or `undefined` for a
 * 204). Throws `ApiError`/`RateLimitError` for any non-2xx response.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (options.sessionRequired) {
    await bootstrapSession();
  }

  const timeoutController = options.timeoutMs !== undefined ? new AbortController() : undefined;
  const timeoutId =
    timeoutController && options.timeoutMs !== undefined
      ? setTimeout(() => timeoutController.abort(), options.timeoutMs)
      : undefined;
  const signal = options.signal ?? timeoutController?.signal;

  try {
    let response = await fetch(path, buildRequestInit(options, signal));

    if (response.status === 401 && options.sessionRequired) {
      await forceResessionBootstrap();
      response = await fetch(path, buildRequestInit(options, signal));
    }

    if (!response.ok) {
      throw await toApiError(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }
}

/** Exposed for tests only -- resets the module-level single-flight state. */
export function _resetSessionBootstrapForTests(): void {
  sessionBootstrapPromise = null;
}
