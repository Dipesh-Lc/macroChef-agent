/**
 * Fetch-based Server-Sent Events parser (ROADMAP.md Step 4.2, consuming
 * `POST /recipes/recommend/stream` from Step 3.1 -- `app/api/routes_stream.py`).
 *
 * Browsers' native `EventSource` only supports `GET` requests; this
 * endpoint is `POST` (same request body as the synchronous
 * `POST /recipes/recommend`), so there is no native client for it. This
 * module hand-rolls the wire format instead: `parseSseStream` reads a
 * `ReadableStream<Uint8Array>` and yields `{event, data}` pairs as
 * complete events arrive, and `streamRecommend` wires that parser to
 * `apiStream` (`app/api/client.ts`) and discriminates the three event
 * types the backend actually emits today (`node`, `result`, `error` --
 * see `app.api.routes_stream`'s docstring). It does NOT handle an
 * `awaiting_input` event type -- that's ROADMAP Step 3.2/4.2's deferred
 * HITL work; the current backend never emits it, and any future/unknown
 * event type is silently ignored here rather than guessed at.
 *
 * Design choice -- async generator, not a callback/subscribe API: an
 * async generator composes directly with `for await...of` in a React
 * effect/event handler, gives the caller natural backpressure (the
 * generator only reads the next network chunk once the consumer asks for
 * the next value), and cleans itself up on early exit (`break`/`return`
 * inside the loop triggers this generator's `finally`, releasing the
 * stream's lock) without a separate `unsubscribe` handle to remember to
 * call.
 */

import { apiStream } from "../api/client";
import type { RecommendationRequest, RecommendationResponse } from "../api/types";

// ROADMAP.md Step 4.3: the Chef chat turn stream (`POST /chat/{thread_id}/
// message`, `app.api.routes_chat._stream_chat_turn`). Same POST-SSE
// transport/heartbeat contract as `streamRecommend` below (this backend
// module mirrors `app.api.routes_stream`'s worker-thread + polling
// architecture byte-for-byte, per that module's own docstring), so this
// reuses the identical `parseSseStream` + `apiStream` plumbing rather than a
// second parser.

/** One `RunEvent` (`app.observability.events.RunEvent`) relayed live as a
 * `node` SSE event -- see that Pydantic model for the authoritative shape;
 * this is its JSON-serialized (`mode="json"`) form. */
export interface NodeRunEvent {
  run_id: string;
  node: string;
  status: "started" | "finished" | "failed";
  elapsed_ms: number | null;
  summary: string;
  payload: Record<string, unknown>;
  ts: string;
}

/** The terminal `error` event's payload -- see `app.api.routes_stream._stream_recommend`'s
 * docstring: deliberately generic, never the raw exception message. */
export interface StreamErrorEvent {
  detail: string;
  error_type: string;
}

/** One parsed, typed event from the recommend stream. Every event carries a
 * `type` discriminant matching the SSE `event:` line so callers can
 * `switch`/narrow without re-checking the raw string. */
export type RecommendStreamEvent =
  | { type: "node"; data: NodeRunEvent }
  | { type: "result"; data: RecommendationResponse }
  | { type: "error"; data: StreamErrorEvent };

/** One raw, untyped SSE event -- `event:` line value plus its JSON-parsed
 * `data:` payload. Low-level building block `streamRecommend` (below) wraps;
 * exported for direct testing/reuse against any future POST-SSE endpoint. */
export interface SseEvent<T = unknown> {
  event: string;
  data: T;
}

/**
 * Read a `ReadableStream<Uint8Array>` of SSE-framed bytes and yield each
 * complete event as it arrives.
 *
 * Per the SSE wire format this project's backend writes (`app.api.
 * routes_stream._sse`): events are separated by a blank line (`\n\n`);
 * within one event, an `event: <type>` line sets the type and one or more
 * `data: <json-fragment>` lines carry the payload (joined with `\n` before
 * parsing, per spec -- this backend only ever writes one `data:` line per
 * event, but multi-line `data:` is valid SSE and cheap to support
 * correctly); any line starting with `:` (this backend's `: heartbeat`
 * comment, sent every ~10s of silence -- see `HEARTBEAT_INTERVAL_SECONDS`
 * in `app/api/routes_stream.py`) is ignored, not yielded. A `data:` line
 * whose JSON fails to parse causes that one event to be dropped rather than
 * throwing -- a single malformed event should never kill an otherwise-live
 * stream the rest of a long recommend run still depends on.
 */
export async function* parseSseStream<T = unknown>(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent<T>> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }

      // Flush every complete event block currently buffered -- a single
      // chunk can contain more than one event (the backend batches
      // whatever the sink accumulated between polls), and conversely one
      // event can arrive split across chunks, which is why this re-scans
      // `buffer` from the top on every read rather than assuming one
      // event per chunk.
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseEventBlock<T>(rawEvent);
        if (parsed) {
          yield parsed;
        }
        boundary = buffer.indexOf("\n\n");
      }

      if (done) {
        // The stream closed -- flush one last time in case the final
        // event had no trailing blank line before the connection ended.
        const parsed = parseEventBlock<T>(buffer);
        if (parsed) {
          yield parsed;
        }
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseEventBlock<T>(rawEvent: string): SseEvent<T> | null {
  let eventType: string | null = null;
  const dataLines: string[] = [];

  for (const line of rawEvent.split("\n")) {
    if (line === "" || line.startsWith(":")) {
      continue; // blank padding within the block, or a comment/heartbeat line
    }
    if (line.startsWith("event: ")) {
      eventType = line.slice("event: ".length);
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice("data: ".length));
    }
  }

  if (eventType === null || dataLines.length === 0) {
    return null;
  }

  try {
    return { event: eventType, data: JSON.parse(dataLines.join("\n")) as T };
  } catch {
    return null;
  }
}

/** Same generous budget `recommendRecipes` (`api/endpoints.ts`) gives the
 * synchronous sibling endpoint -- not enforced as a hard `apiStream`
 * timeout (see that function's docstring for why), but documented here so
 * a caller building its own idle watchdog around this generator has a
 * reference figure consistent with the rest of the app. */
export const RECOMMEND_STREAM_IDLE_REFERENCE_MS = 90_000;

/**
 * Stream `POST /recipes/recommend/stream` (session-gated, same request
 * body as `recommendRecipes`) and yield each relayed `node` event live,
 * ending with exactly one `result` or `error` event -- mirrors the
 * backend's own terminal-event contract (see `app.api.routes_stream`'s
 * docstring). Any SSE event type this parser doesn't recognize (there are
 * none today besides `node`/`result`/`error`) is silently skipped rather
 * than yielded as an untyped event, so callers never have to guard against
 * a shape they don't understand.
 */
export async function* streamRecommend(
  request: RecommendationRequest,
  signal?: AbortSignal,
): AsyncGenerator<RecommendStreamEvent> {
  const response = await apiStream("/recipes/recommend/stream", {
    method: "POST",
    json: request,
    sessionRequired: true,
    signal,
  });

  if (!response.body) {
    throw new Error("Streaming response had no readable body");
  }

  for await (const { event, data } of parseSseStream(response.body)) {
    if (event === "node") {
      yield { type: "node", data: data as NodeRunEvent };
    } else if (event === "result") {
      yield { type: "result", data: data as RecommendationResponse };
    } else if (event === "error") {
      yield { type: "error", data: data as StreamErrorEvent };
    }
    // Unknown/future event type (e.g. a later `awaiting_input`, ROADMAP
    // Step 3.2) -- deliberately ignored, not yielded; see module docstring.
  }
}

// ---------------------------------------------------------------------------
// Chef chat turn stream (ROADMAP.md Step 4.3, consuming `POST /chat/
// {thread_id}/message` from Step 3.3 -- `app.api.routes_chat`).
// ---------------------------------------------------------------------------

/** One live `tool_call` SSE event -- `app.agent.chef_agent.tools_node` emits
 * this the instant a tool starts executing, before its result exists. */
export interface ChatToolCallEvent {
  tool: string;
  args_summary: string;
  call_id: string;
}

/** One live `tool_result` SSE event, correlated to its `tool_call` sibling
 * by `call_id`. `raw` is the tool's own small JSON-serializable payload
 * (`app.agent.tools.ToolResult.raw`) -- shape varies per tool, see
 * `ToolCallChip`'s per-tool rendering. */
export interface ChatToolResultEvent {
  call_id: string;
  summary: string;
  raw: Record<string, unknown>;
}

/** The terminal turn's answer, carried as a SINGLE `token` event -- see
 * `app.api.routes_chat._stream_chat_turn`'s docstring: `generate_structured`
 * is one blocking structured call, not a token-streaming API, so this event
 * delivers the whole final answer in one `delta` rather than fabricating
 * incremental deltas. Kept as its own event type (rather than folded into
 * `message` below) so the wire vocabulary stays ready for real incremental
 * streaming later without a breaking change. */
export interface ChatTokenEvent {
  delta: string;
}

/** The terminal `message` event -- same content as the `token` event's
 * `delta` (this backend always emits exactly one of each per turn, `token`
 * first), plus this turn's full tool-call history for callers that want it. */
export interface ChatMessageEvent {
  role: "assistant";
  content: string;
  tool_calls: Record<string, unknown>[] | null;
}

/** One parsed, typed event from the chat turn stream. */
export type ChatStreamEvent =
  | { type: "tool_call"; data: ChatToolCallEvent }
  | { type: "tool_result"; data: ChatToolResultEvent }
  | { type: "token"; data: ChatTokenEvent }
  | { type: "message"; data: ChatMessageEvent }
  | { type: "error"; data: StreamErrorEvent };

/**
 * Stream `POST /chat/{thread_id}/message` (session-gated, rate-limited --
 * see `app.dependencies.require_chat_message_rate_limit`) and yield each
 * relayed event live: zero or more `tool_call`/`tool_result` pairs (in
 * arrival order -- a `tool_call` always precedes its matching `tool_result`,
 * see `app.agent.chef_agent.tools_node`), then exactly one `token` and one
 * terminal `message`, OR one terminal `error`. Any unrecognized SSE event
 * type is silently skipped, mirroring `streamRecommend`'s same forward-
 * compatibility posture above.
 */
export async function* streamChatMessage(
  threadId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const response = await apiStream(`/chat/${encodeURIComponent(threadId)}/message`, {
    method: "POST",
    json: { message },
    sessionRequired: true,
    signal,
  });

  if (!response.body) {
    throw new Error("Streaming response had no readable body");
  }

  for await (const { event, data } of parseSseStream(response.body)) {
    if (event === "tool_call") {
      yield { type: "tool_call", data: data as ChatToolCallEvent };
    } else if (event === "tool_result") {
      yield { type: "tool_result", data: data as ChatToolResultEvent };
    } else if (event === "token") {
      yield { type: "token", data: data as ChatTokenEvent };
    } else if (event === "message") {
      yield { type: "message", data: data as ChatMessageEvent };
    } else if (event === "error") {
      yield { type: "error", data: data as StreamErrorEvent };
    }
  }
}
