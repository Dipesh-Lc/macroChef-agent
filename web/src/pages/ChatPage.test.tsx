import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatStreamEvent } from "../lib/sse";
import type { ChatThreadStatusResponse, Recipe } from "../api/types";
import { CHAT_THREADS_STORAGE_KEY } from "../lib/chatThreads";
import ChatPage from "./ChatPage";

vi.mock("../api/endpoints", () => ({
  createChatThread: vi.fn(),
  getChatThread: vi.fn(),
  getRecipe: vi.fn(),
}));

// `streamChatMessage` (ROADMAP Step 4.3) is mocked here (rather than faking
// a raw `Response`/`ReadableStream`) so each test can script exactly which
// typed events arrive and when -- same "controlled generator" technique
// `HomePage.test.tsx` uses for `streamRecommend`.
vi.mock("../lib/sse", () => ({
  streamChatMessage: vi.fn(),
}));

import { createChatThread, getChatThread, getRecipe } from "../api/endpoints";
import { streamChatMessage } from "../lib/sse";

function controlledStream() {
  const queue: ChatStreamEvent[] = [];
  let wake: (() => void) | null = null;
  let finished = false;

  async function* generator(): AsyncGenerator<ChatStreamEvent> {
    while (true) {
      if (queue.length > 0) {
        yield queue.shift() as ChatStreamEvent;
        continue;
      }
      if (finished) {
        return;
      }
      await new Promise<void>((resolve) => {
        wake = resolve;
      });
    }
  }

  return {
    generator,
    push(event: ChatStreamEvent) {
      queue.push(event);
      wake?.();
      wake = null;
    },
    finish() {
      finished = true;
      wake?.();
      wake = null;
    },
  };
}

function renderChatPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ChatPage />
    </QueryClientProvider>,
  );
}

function seedExistingThread(threadId = "thread_1") {
  window.localStorage.setItem(
    CHAT_THREADS_STORAGE_KEY,
    JSON.stringify([{ threadId, title: null, createdAt: "2026-01-01T00:00:00Z" }]),
  );
}

function emptyThreadStatus(threadId: string): ChatThreadStatusResponse {
  return { thread_id: threadId, title: null, messages: [] };
}

function buildRecipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    recipe_id: "recipe_1",
    title: "Lentil Soup",
    ingredients: [],
    instructions: ["Cook."],
    nutrition: null,
    servings: 2,
    source_type: "imported",
    is_user_saved: false,
    is_active: true,
    restored_from_quarantine: false,
    derived_allergens: [],
    ...overrides,
  };
}

async function startTurn(message: string) {
  fireEvent.change(screen.getByPlaceholderText(/ask chef anything/i), {
    target: { value: message },
  });
  fireEvent.click(screen.getByRole("button", { name: /^send$/i }));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(createChatThread).mockReset();
  vi.mocked(getChatThread).mockReset();
  vi.mocked(getRecipe).mockReset();
  vi.mocked(streamChatMessage).mockReset();
});

describe("ChatPage profile gate (CLAUDE.md invariant #1 -- allergies must be set before any message)", () => {
  it("shows the profile form (never a composer) until a thread has been created, then reveals the composer", async () => {
    vi.mocked(createChatThread).mockResolvedValue({ thread_id: "new_thread" });
    renderChatPage();

    expect(screen.getByRole("button", { name: /start chat/i })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/ask chef anything/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /start chat/i }));

    await waitFor(() =>
      expect(screen.getByPlaceholderText(/ask chef anything/i)).toBeInTheDocument(),
    );
    expect(vi.mocked(createChatThread)).toHaveBeenCalledTimes(1);
    // The profile actually sent is a real UserProfile (defaults, since the
    // form wasn't edited in this test) -- never an empty/omitted profile.
    const [request] = vi.mocked(createChatThread).mock.calls[0];
    expect(request.user_profile).toBeDefined();
    expect(Array.isArray(request.user_profile.allergies)).toBe(true);
  });
});

describe("ChatPage live turn streaming (ROADMAP 4.3 acceptance test)", () => {
  it("renders tool-call chips before the final assistant text lands", async () => {
    seedExistingThread("thread_1");
    vi.mocked(getChatThread).mockResolvedValue(emptyThreadStatus("thread_1"));
    const stream = controlledStream();
    vi.mocked(streamChatMessage).mockImplementation(() => stream.generator());

    renderChatPage();
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/ask chef anything/i)).toBeInTheDocument(),
    );

    await startTurn("Suggest a safe dinner");

    act(() =>
      stream.push({
        type: "tool_call",
        data: { tool: "search_recipes", args_summary: "Searching recipes.", call_id: "c1" },
      }),
    );
    await waitFor(() => expect(screen.getByText("Searching recipes.")).toBeInTheDocument());
    expect(screen.queryByText("Here is a safe option.")).not.toBeInTheDocument();

    act(() =>
      stream.push({
        type: "tool_result",
        data: { call_id: "c1", summary: "Found 1 recipe(s): Lentil Soup.", raw: { recipes: [] } },
      }),
    );
    await waitFor(() =>
      expect(screen.getByText(/Found 1 recipe\(s\): Lentil Soup\./)).toBeInTheDocument(),
    );
    // The chip is visible -- the final answer still hasn't landed.
    expect(screen.queryByText("Here is a safe option.")).not.toBeInTheDocument();

    act(() => {
      stream.push({ type: "token", data: { delta: "Here is a safe option." } });
      stream.push({
        type: "message",
        data: { role: "assistant", content: "Here is a safe option.", tool_calls: [] },
      });
      stream.finish();
    });

    await waitFor(() => expect(screen.getByText("Here is a safe option.")).toBeInTheDocument());
    // The chip stays visible, and precedes the final text in document order.
    const chip = screen.getByText(/Found 1 recipe\(s\): Lentil Soup\./);
    const finalText = screen.getByText("Here is a safe option.");
    expect(chip.compareDocumentPosition(finalText) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders the existing RecipeCard from a tool result's recipe data, via 'View recipe'", async () => {
    seedExistingThread("thread_1");
    vi.mocked(getChatThread).mockResolvedValue(emptyThreadStatus("thread_1"));
    vi.mocked(getRecipe).mockResolvedValue(buildRecipe());
    const stream = controlledStream();
    vi.mocked(streamChatMessage).mockImplementation(() => stream.generator());

    renderChatPage();
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/ask chef anything/i)).toBeInTheDocument(),
    );

    await startTurn("Find me a recipe");

    act(() =>
      stream.push({
        type: "tool_call",
        data: { tool: "search_recipes", args_summary: "Searching recipes.", call_id: "c1" },
      }),
    );
    act(() =>
      stream.push({
        type: "tool_result",
        data: {
          call_id: "c1",
          summary: "Found 1 recipe(s): Lentil Soup.",
          raw: {
            recipes: [
              { recipe_id: "recipe_1", title: "Lentil Soup", cuisine: "Any", meal_type: "dinner" },
            ],
          },
        },
      }),
    );
    act(() => {
      stream.push({ type: "token", data: { delta: "Try the Lentil Soup." } });
      stream.push({
        type: "message",
        data: { role: "assistant", content: "Try the Lentil Soup.", tool_calls: [] },
      });
      stream.finish();
    });

    await waitFor(() =>
      expect(screen.getByText(/Found 1 recipe\(s\): Lentil Soup\./)).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /search_recipes/ }));
    fireEvent.click(screen.getByRole("button", { name: /view recipe/i }));

    await waitFor(() => expect(vi.mocked(getRecipe)).toHaveBeenCalledWith("recipe_1"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    // The real RecipeCard rendered inside the modal (its title heading).
    expect(screen.getByRole("heading", { name: "Lentil Soup" })).toBeInTheDocument();
  });
});
