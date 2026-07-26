import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, RateLimitError, _resetSessionBootstrapForTests, apiRequest } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptyResponse(status: number): Response {
  return new Response(null, { status });
}

describe("apiRequest", () => {
  beforeEach(() => {
    _resetSessionBootstrapForTests();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("bootstraps the session exactly once for concurrent session-required calls (single-flight)", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/session") {
        return emptyResponse(204);
      }
      return jsonResponse(200, { ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([
      apiRequest("/recipes/recommend", { method: "POST", json: {}, sessionRequired: true }),
      apiRequest("/feedback", { method: "POST", json: {}, sessionRequired: true }),
    ]);

    const sessionCalls = fetchMock.mock.calls.filter(([input]) => String(input) === "/session");
    expect(sessionCalls).toHaveLength(1);
  });

  it("sends the CSRF header only on session-required calls", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/session") {
        return emptyResponse(204);
      }
      return jsonResponse(200, { ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/plan/day", { method: "POST", json: {} }); // public call
    await apiRequest("/recipes/recommend", {
      method: "POST",
      json: {},
      sessionRequired: true,
    });

    const publicCall = fetchMock.mock.calls.find(([input]) => String(input) === "/plan/day");
    const sessionCall = fetchMock.mock.calls.find(([input]) => String(input) === "/recipes/recommend");

    const publicHeaders = publicCall?.[1]?.headers as Headers;
    const sessionHeaders = sessionCall?.[1]?.headers as Headers;

    expect(publicHeaders.has("X-Requested-With")).toBe(false);
    expect(sessionHeaders.get("X-Requested-With")).toBe("MacroChef");
  });

  it("re-mints the session once on a 401 and retries the original request exactly once", async () => {
    let recommendAttempts = 0;
    let sessionMints = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/session") {
        sessionMints += 1;
        return emptyResponse(204);
      }
      if (url === "/recipes/recommend") {
        recommendAttempts += 1;
        if (recommendAttempts === 1) {
          return jsonResponse(401, { detail: "Missing session token" });
        }
        return jsonResponse(200, { recommendations: [] });
      }
      throw new Error(`unexpected url ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequest("/recipes/recommend", {
      method: "POST",
      json: {},
      sessionRequired: true,
    });

    expect(result).toEqual({ recommendations: [] });
    expect(recommendAttempts).toBe(2);
    expect(sessionMints).toBe(2); // initial bootstrap + forced re-mint after the 401
  });

  it("surfaces a second consecutive 401 as an ApiError, with no infinite retry loop", async () => {
    let recommendAttempts = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/session") {
        return emptyResponse(204);
      }
      if (url === "/recipes/recommend") {
        recommendAttempts += 1;
        return jsonResponse(401, { detail: "Invalid session token" });
      }
      throw new Error(`unexpected url ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiRequest("/recipes/recommend", { method: "POST", json: {}, sessionRequired: true }),
    ).rejects.toMatchObject({ status: 401 });

    expect(recommendAttempts).toBe(2); // exactly one retry -- never more
  });

  it("types a 429 response as RateLimitError with the user-facing message", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/session") {
        return emptyResponse(204);
      }
      return jsonResponse(429, { detail: "Rate limit exceeded" });
    });
    vi.stubGlobal("fetch", fetchMock);

    const error: unknown = await apiRequest("/recipes/recommend", {
      method: "POST",
      json: {},
      sessionRequired: true,
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(RateLimitError);
    expect((error as RateLimitError).status).toBe(429);
    expect((error as RateLimitError).message).toBe(
      "You're sending requests too quickly — wait a moment and try again.",
    );
  });

  it("throws a plain ApiError for other non-2xx responses", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: "boom" }));
    vi.stubGlobal("fetch", fetchMock);

    const error: unknown = await apiRequest("/inventory/extract", {
      method: "POST",
      body: new URLSearchParams(),
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(500);
    expect((error as ApiError).message).toBe("boom");
  });

  it("aborts the fetch via the timeout controller even when a caller signal is also supplied", async () => {
    const callerController = new AbortController(); // never aborted by this test
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        const signal = init?.signal;
        if (signal?.aborted) {
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiRequest("/plan/day", {
        method: "POST",
        json: {},
        signal: callerController.signal,
        timeoutMs: 5,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it("never sends the CSRF header or bootstraps a session for a public call", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(200, []),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/inventory/extract", { method: "POST", body: new URLSearchParams() });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Headers;
    expect(headers.has("X-Requested-With")).toBe(false);
  });
});
