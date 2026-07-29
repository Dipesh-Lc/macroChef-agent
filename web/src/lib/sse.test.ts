import { afterEach, describe, expect, it, vi } from "vitest";
import { parseSseStream, streamChatMessage, streamRecommend, type SseEvent } from "./sse";

vi.mock("../api/client", () => ({
  apiStream: vi.fn(),
}));

import { apiStream } from "../api/client";

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

async function collect<T>(stream: ReadableStream<Uint8Array>): Promise<SseEvent<T>[]> {
  const out: SseEvent<T>[] = [];
  for await (const event of parseSseStream<T>(stream)) {
    out.push(event);
  }
  return out;
}

describe("parseSseStream", () => {
  it("parses multiple events framed with blank-line boundaries, one chunk per read", async () => {
    const stream = streamFromChunks([
      'event: node\ndata: {"node":"intake_node","status":"started"}\n\n',
      'event: node\ndata: {"node":"intake_node","status":"finished"}\n\n',
      'event: result\ndata: {"recommendations":[]}\n\n',
    ]);

    const events = await collect(stream);

    expect(events).toEqual([
      { event: "node", data: { node: "intake_node", status: "started" } },
      { event: "node", data: { node: "intake_node", status: "finished" } },
      { event: "result", data: { recommendations: [] } },
    ]);
  });

  it("reassembles one event split across multiple chunks", async () => {
    const stream = streamFromChunks([
      "event: no",
      'de\ndata: {"node":"safety_filt',
      'er_node","status":"finished"}',
      "\n\n",
    ]);

    const events = await collect(stream);

    expect(events).toEqual([
      { event: "node", data: { node: "safety_filter_node", status: "finished" } },
    ]);
  });

  it("ignores heartbeat/comment lines, never yielding them as events", async () => {
    const stream = streamFromChunks([
      ": heartbeat\n\n",
      'event: node\ndata: {"node":"x"}\n\n',
      ": heartbeat\n\n",
    ]);

    const events = await collect(stream);

    expect(events).toEqual([{ event: "node", data: { node: "x" } }]);
  });

  it("parses multiple events delivered in a single chunk", async () => {
    const stream = streamFromChunks([
      'event: node\ndata: {"n":1}\n\nevent: node\ndata: {"n":2}\n\n',
    ]);

    const events = await collect(stream);

    expect(events).toEqual([
      { event: "node", data: { n: 1 } },
      { event: "node", data: { n: 2 } },
    ]);
  });

  it("flushes a final event with no trailing blank line once the stream closes", async () => {
    const stream = streamFromChunks(['event: result\ndata: {"ok":true}']);

    const events = await collect(stream);

    expect(events).toEqual([{ event: "result", data: { ok: true } }]);
  });

  it("drops a single event with malformed JSON rather than throwing", async () => {
    const stream = streamFromChunks([
      "event: node\ndata: {not valid json\n\n",
      'event: node\ndata: {"node":"ok"}\n\n',
    ]);

    const events = await collect(stream);

    expect(events).toEqual([{ event: "node", data: { node: "ok" } }]);
  });
});

describe("streamRecommend", () => {
  afterEach(() => {
    vi.mocked(apiStream).mockReset();
  });

  function fakeResponse(chunks: string[]): Response {
    return { body: streamFromChunks(chunks) } as unknown as Response;
  }

  it("discriminates node/result/error events by their SSE `event:` type", async () => {
    vi.mocked(apiStream).mockResolvedValue(
      fakeResponse([
        'event: node\ndata: {"run_id":"r1","node":"intake_node","status":"started","elapsed_ms":null,"summary":"intake_node: started.","payload":{},"ts":"2026-01-01T00:00:00Z"}\n\n',
        'event: result\ndata: {"recommendations":[],"rejected_recipes":[],"shopping_list":[],"errors":[]}\n\n',
      ]),
    );

    const events = [];
    for await (const event of streamRecommend({} as never)) {
      events.push(event);
    }

    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ type: "node", data: { node: "intake_node" } });
    expect(events[1]).toMatchObject({ type: "result", data: { recommendations: [] } });
  });

  it("yields a typed error event for a mid-graph failure", async () => {
    vi.mocked(apiStream).mockResolvedValue(
      fakeResponse(['event: error\ndata: {"detail":"Internal Server Error","error_type":"RuntimeError"}\n\n']),
    );

    const events = [];
    for await (const event of streamRecommend({} as never)) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "error", data: { detail: "Internal Server Error", error_type: "RuntimeError" } },
    ]);
  });

  it("throws if the response has no readable body", async () => {
    vi.mocked(apiStream).mockResolvedValue({ body: null } as unknown as Response);

    await expect(async () => {
      for await (const _event of streamRecommend({} as never)) {
        // no-op -- the generator should throw before yielding anything
      }
    }).rejects.toThrow(/no readable body/);
  });
});

describe("streamChatMessage", () => {
  afterEach(() => {
    vi.mocked(apiStream).mockReset();
  });

  function fakeResponse(chunks: string[]): Response {
    return { body: streamFromChunks(chunks) } as unknown as Response;
  }

  it("discriminates tool_call/tool_result/token/message events by their SSE `event:` type, in arrival order", async () => {
    vi.mocked(apiStream).mockResolvedValue(
      fakeResponse([
        'event: tool_call\ndata: {"tool":"search_recipes","args_summary":"Searching recipes.","call_id":"c1"}\n\n',
        'event: tool_result\ndata: {"call_id":"c1","summary":"Found 1 recipe(s).","raw":{}}\n\n',
        'event: token\ndata: {"delta":"Here you go."}\n\n',
        'event: message\ndata: {"role":"assistant","content":"Here you go.","tool_calls":[]}\n\n',
      ]),
    );

    const events = [];
    for await (const event of streamChatMessage("thread_1", "hi")) {
      events.push(event);
    }

    expect(events.map((event) => event.type)).toEqual(["tool_call", "tool_result", "token", "message"]);
    expect(events[0]).toMatchObject({ type: "tool_call", data: { tool: "search_recipes" } });
    expect(events[3]).toMatchObject({ type: "message", data: { content: "Here you go." } });
  });

  it("yields a typed error event for a mid-turn failure", async () => {
    vi.mocked(apiStream).mockResolvedValue(
      fakeResponse(['event: error\ndata: {"detail":"Internal Server Error","error_type":"RuntimeError"}\n\n']),
    );

    const events = [];
    for await (const event of streamChatMessage("thread_1", "hi")) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "error", data: { detail: "Internal Server Error", error_type: "RuntimeError" } },
    ]);
  });

  it("posts to /chat/{thread_id}/message with the message body, session-required", async () => {
    vi.mocked(apiStream).mockResolvedValue(fakeResponse([]));

    for await (const _event of streamChatMessage("thread_1", "hello chef")) {
      // no-op -- draining the (empty) stream
    }

    expect(apiStream).toHaveBeenCalledWith(
      "/chat/thread_1/message",
      expect.objectContaining({
        method: "POST",
        json: { message: "hello chef" },
        sessionRequired: true,
      }),
    );
  });

  it("throws if the response has no readable body", async () => {
    vi.mocked(apiStream).mockResolvedValue({ body: null } as unknown as Response);

    await expect(async () => {
      for await (const _event of streamChatMessage("thread_1", "hi")) {
        // no-op -- the generator should throw before yielding anything
      }
    }).rejects.toThrow(/no readable body/);
  });
});
