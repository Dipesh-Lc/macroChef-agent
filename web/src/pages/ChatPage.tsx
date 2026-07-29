import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { DisclaimerBanner } from "../components/DisclaimerBanner";
import { ProfileForm } from "../components/ProfileForm";
import { RecipeDetailModal } from "../components/RecipeDetailModal";
import { ChatMessage, type ChatTranscriptRow } from "../components/ChatMessage";
import type { ToolCallChipData } from "../components/ToolCallChip";
import { ApiError, NotFoundError, RateLimitError } from "../api/client";
import { createChatThread, getChatThread } from "../api/endpoints";
import { streamChatMessage } from "../lib/sse";
import type { ChatMessageView, UserProfile } from "../api/types";
import {
  addChatThread,
  loadChatThreads,
  removeChatThread,
  updateChatThreadTitle,
  type ChatThreadSummary,
} from "../lib/chatThreads";

/**
 * The Chef chat UI (ROADMAP.md Step 4.3, consuming the tool-calling agent
 * from Step 3.3 -- `app/api/routes_chat.py`).
 *
 * SAFETY-RELEVANT DESIGN CALL (flagged per the task spec, CLAUDE.md
 * invariant #1): `POST /chat` binds a `UserProfile` (allergies, diet type,
 * macro targets) ONCE, at thread-creation time, and it can never be changed
 * afterward (see `app.data.models.ChatThread`'s docstring). This page
 * therefore NEVER mints a new thread with a default/empty profile -- the
 * profile gate below (reusing `ProfileForm` verbatim, the same allergy tag
 * input the planner page uses) is mandatory and blocking: there is no
 * message input, no way to talk to Chef at all, until a profile has been
 * confirmed via "Start chat". Selecting an EXISTING thread from the sidebar
 * skips the gate (that thread's profile was already bound when it was
 * created) but never lets a new thread skip it.
 *
 * Thread list: localStorage-backed (see `lib/chatThreads.ts`) -- the
 * backend has no "list my threads" endpoint, only create-by-id and
 * fetch-by-id, so this browser's own record is the only source of "which
 * threads exist to switch between" (ROADMAP's own text calls this out).
 */

interface PersistedToolCallEntry {
  tool?: string;
  ok?: boolean;
  summary?: string;
  raw?: Record<string, unknown>;
  error?: string | null;
}

function messagesToRows(messages: ChatMessageView[]): ChatTranscriptRow[] {
  return messages.map((message, index) => {
    const id = `hist-${index}`;
    if (message.role === "tool") {
      const entry = (message.tool_calls?.[0] ?? {}) as PersistedToolCallEntry;
      const call: ToolCallChipData = {
        callId: id,
        tool: entry.tool ?? "unknown",
        result: { summary: entry.summary ?? message.content, raw: entry.raw ?? {} },
        ok: entry.ok,
        error: entry.error ?? null,
      };
      return { kind: "tool", id, call };
    }
    if (message.role === "user") {
      return { kind: "user", id, content: message.content };
    }
    return { kind: "assistant", id, content: message.content };
  });
}

function friendlyErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof RateLimitError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return fallback;
}

export default function ChatPage() {
  // Lazy initializers (not an effect): localStorage is read synchronously
  // exactly once, during the first render -- same convention `ProfileForm`
  // already uses for its own localStorage-backed state -- so there is never
  // a render with an empty thread list immediately followed by a second
  // render once the "real" value loads, and the mount effect below never
  // needs to call `setThreads`/`setShowProfileGate` directly (which would
  // trip `react-hooks/set-state-in-effect`).
  const [threads, setThreads] = useState<ChatThreadSummary[]>(() => loadChatThreads());
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<ChatTranscriptRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [showProfileGate, setShowProfileGate] = useState<boolean>(() => loadChatThreads().length === 0);
  const [draftProfile, setDraftProfile] = useState<UserProfile | null>(null);
  const [creatingThread, setCreatingThread] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [rateLimitMessage, setRateLimitMessage] = useState<string | null>(null);

  const [viewRecipeId, setViewRecipeId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const loadThread = useCallback(async (threadId: string) => {
    setHistoryLoading(true);
    setHistoryError(null);
    setStreamError(null);
    setShowProfileGate(false);
    try {
      const status = await getChatThread(threadId);
      setActiveThreadId(threadId);
      setTranscript(messagesToRows(status.messages ?? []));
    } catch (error) {
      if (error instanceof NotFoundError) {
        // Stale localStorage entry -- this browser's record of "threads
        // that exist" can never be reconciled with the server (no list
        // endpoint, see `lib/chatThreads.ts`'s docstring), so drop it and
        // fall back to the profile gate rather than showing a dead thread.
        setThreads((current) => removeChatThread(current, threadId));
        setActiveThreadId(null);
        setTranscript([]);
        setShowProfileGate(true);
        setHistoryError("That conversation could not be found anymore.");
        return;
      }
      setHistoryError(
        friendlyErrorMessage(error, "Could not load this conversation. Please try again."),
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (threads.length === 0) {
      return;
    }
    // Mount-once bootstrap: `threads`'s initial value already reflects
    // localStorage (see the lazy initializer above), so this effect's only
    // job is kicking off the async load of the most-recent thread's
    // history. Deferred one macrotask via `setTimeout` (same technique this
    // file's own rate-limit-toast effect below uses) so `loadThread`'s
    // synchronous setState prefix never runs inside this effect's own
    // commit -- `react-hooks/set-state-in-effect` flags that even through a
    // called function, and correctly so: an effect body should schedule
    // work, not itself synchronously cascade a render.
    const timer = setTimeout(() => void loadThread(threads[0].threadId), 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-once bootstrap only; re-running on every `threads`/`loadThread` identity change would re-select thread 0 on every unrelated list update.
  }, []);

  // Cancel any in-flight turn on unmount -- never leave a stream reading
  // into state that no longer exists.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  function handleNewChatClick() {
    // Never let a turn still streaming for the thread being left behind go
    // on appending its `tool_call`/`token`/... rows onto whatever renders
    // next -- same "cancel on the way out" contract as the unmount effect
    // above.
    abortRef.current?.abort();
    setShowProfileGate(true);
    setSidebarOpen(false);
    setHistoryError(null);
  }

  function handleSelectThread(threadId: string) {
    abortRef.current?.abort();
    setSidebarOpen(false);
    void loadThread(threadId);
  }

  async function handleStartChat() {
    if (!draftProfile) {
      return;
    }
    setCreatingThread(true);
    setCreateError(null);
    try {
      const response = await createChatThread({ user_profile: draftProfile });
      const summary: ChatThreadSummary = {
        threadId: response.thread_id,
        title: null,
        createdAt: new Date().toISOString(),
      };
      setThreads((current) => addChatThread(current, summary));
      setActiveThreadId(response.thread_id);
      setTranscript([]);
      setShowProfileGate(false);
    } catch (error) {
      setCreateError(friendlyErrorMessage(error, "Could not start a new chat. Please try again."));
    } finally {
      setCreatingThread(false);
    }
  }

  function maybeUpdateThreadTitle(threadId: string, rawMessage: string) {
    setThreads((current) => {
      const existing = current.find((thread) => thread.threadId === threadId);
      if (existing?.title) {
        return current;
      }
      // Mirrors `ChatThreadRepository.set_title_if_unset` exactly: the
      // server sets `title = message[:256]` verbatim the first time a
      // thread gets a title, and never changes it again -- this optimistic
      // local update can never drift from what the server will report.
      return updateChatThreadTitle(current, threadId, rawMessage.slice(0, 256));
    });
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = inputValue.trim();
    if (!message || !activeThreadId || isStreaming) {
      return;
    }
    const threadId = activeThreadId;

    setInputValue("");
    setStreamError(null);
    setTranscript((current) => [
      ...current,
      { kind: "user", id: `user-${Date.now()}`, content: message },
    ]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let receivedAnyEvent = false;

    try {
      for await (const streamEvent of streamChatMessage(threadId, message, controller.signal)) {
        receivedAnyEvent = true;
        if (streamEvent.type === "tool_call") {
          const call: ToolCallChipData = {
            callId: streamEvent.data.call_id,
            tool: streamEvent.data.tool,
            argsSummary: streamEvent.data.args_summary,
          };
          setTranscript((current) => [
            ...current,
            { kind: "tool", id: call.callId, call },
          ]);
        } else if (streamEvent.type === "tool_result") {
          // The live `tool_result` SSE event carries only `{call_id, summary,
          // raw}` -- `ToolResult.ok`/`.error` are NOT relayed live (see
          // `app.agent.chef_agent.tools_node`'s `_emit_chat_event` call), so
          // `call.ok` intentionally stays `undefined` here (never guessed at
          // `true`). A genuine tool failure still surfaces honestly: its
          // `summary`/`raw` describe the failure in plain language (see
          // `app.agent.tools`'s module docstring -- a failed tool call never
          // raises, it returns `ok=False` with a human `summary`), it just
          // isn't styled in the chili "failed" treatment until this thread's
          // history is reloaded from `GET /chat/{thread_id}` (which DOES
          // persist `ok`, see `messagesToRows` above).
          setTranscript((current) =>
            current.map((row) =>
              row.kind === "tool" && row.id === streamEvent.data.call_id
                ? {
                    ...row,
                    call: {
                      ...row.call,
                      result: { summary: streamEvent.data.summary, raw: streamEvent.data.raw },
                    },
                  }
                : row,
            ),
          );
        } else if (streamEvent.type === "token") {
          // Currently the whole final answer in one shot (see
          // `streamChatMessage`'s docstring) -- rendered as a draft
          // assistant row so tool chips (already appended above) are always
          // visible before this text lands, matching the ROADMAP's own
          // ordering requirement.
          setTranscript((current) => {
            const withoutDraft = current.filter((row) => row.id !== "draft-assistant");
            return [
              ...withoutDraft,
              { kind: "assistant", id: "draft-assistant", content: streamEvent.data.delta },
            ];
          });
        } else if (streamEvent.type === "message") {
          setTranscript((current) =>
            current.map((row) =>
              row.id === "draft-assistant"
                ? { kind: "assistant", id: `assistant-${Date.now()}`, content: streamEvent.data.content }
                : row,
            ),
          );
          maybeUpdateThreadTitle(threadId, message);
        } else if (streamEvent.type === "error") {
          setStreamError(streamEvent.data.detail);
        }
      }
    } catch (caught) {
      if (caught instanceof RateLimitError) {
        setRateLimitMessage(caught.message);
      } else if (caught instanceof DOMException && caught.name === "AbortError") {
        // Caller-initiated cancellation (unmount) -- not a user-facing error.
      } else if (receivedAnyEvent) {
        setStreamError(friendlyErrorMessage(caught, "Something went wrong. Please try again."));
      } else {
        setStreamError(
          friendlyErrorMessage(caught, "Could not reach Chef right now. Please try again."),
        );
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }

  // Auto-dismiss the rate-limit toast, same convention `HomePage`'s
  // `useRecommendStream` uses for the identical shared-limit UX.
  useEffect(() => {
    if (!rateLimitMessage) {
      return;
    }
    const timeout = setTimeout(() => setRateLimitMessage(null), 6000);
    return () => clearTimeout(timeout);
  }, [rateLimitMessage]);

  const activeThread = threads.find((thread) => thread.threadId === activeThreadId);
  const activeThreadTitle = activeThread?.title ?? "New chat";

  return (
    <div className="flex flex-col gap-4">
      <DisclaimerBanner />

      <div className="relative flex h-[75vh] min-h-[420px] flex-col overflow-hidden rounded-lg border border-sage-line bg-white sm:flex-row">
        {/* Thread sidebar: a full-screen overlay drawer below the `sm`
            breakpoint (toggled by the "Threads" button in the mobile header
            below), a static left column at `sm` and up -- same breakpoint
            convention `TopNav` already uses for its own mobile/desktop split. */}
        <aside
          className={`${
            sidebarOpen ? "flex" : "hidden"
          } absolute inset-0 z-20 flex-col overflow-y-auto bg-porcelain p-3 sm:static sm:z-auto sm:flex sm:w-64 sm:shrink-0 sm:border-r sm:border-sage-line sm:bg-white`}
        >
          <div className="flex items-center justify-between gap-2 pb-2">
            <h2 className="font-display text-sm font-semibold text-cast-iron">Conversations</h2>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="text-xs font-medium text-cast-iron/60 sm:hidden"
            >
              Close
            </button>
          </div>

          <button
            type="button"
            onClick={handleNewChatClick}
            className="mb-2 rounded-md border border-basil px-3 py-1.5 text-left text-sm font-medium text-basil hover:bg-basil/10"
          >
            + New chat
          </button>

          <ul className="flex flex-col gap-1">
            {threads.map((thread) => (
              <li key={thread.threadId}>
                <button
                  type="button"
                  onClick={() => handleSelectThread(thread.threadId)}
                  aria-current={thread.threadId === activeThreadId ? "true" : undefined}
                  className={`w-full truncate rounded-md px-2 py-1.5 text-left text-sm ${
                    thread.threadId === activeThreadId
                      ? "bg-cast-iron text-porcelain"
                      : "text-cast-iron/80 hover:bg-sage-line/60"
                  }`}
                >
                  {thread.title ?? "New chat"}
                </button>
              </li>
            ))}
            {threads.length === 0 && (
              <li className="px-2 py-1.5 text-xs text-cast-iron/50">No conversations yet.</li>
            )}
          </ul>
        </aside>

        {/* Main transcript column */}
        <div className="relative flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between gap-2 border-b border-sage-line px-4 py-2 sm:hidden">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="rounded-md border border-sage-line px-2 py-1 text-xs font-medium text-cast-iron"
            >
              Threads
            </button>
            <span className="truncate text-sm font-medium text-cast-iron">{activeThreadTitle}</span>
          </div>

          {rateLimitMessage && (
            <div className="mx-4 mt-2 rounded-md border border-honey-dark bg-honey/15 px-3 py-2 text-sm text-honey-dark">
              {rateLimitMessage}
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
            {showProfileGate ? (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-cast-iron/70">
                  Set your profile before starting a chat with Chef — your allergies and diet type
                  are attached to this conversation once, and used for every safety check Chef runs
                  in it.
                </p>
                <ProfileForm onProfileChange={setDraftProfile} />
                {createError && <p className="text-sm text-chili">{createError}</p>}
                <button
                  type="button"
                  onClick={() => void handleStartChat()}
                  disabled={creatingThread || !draftProfile}
                  className="w-fit rounded-md bg-cast-iron px-4 py-2 text-sm font-semibold text-porcelain disabled:opacity-50"
                >
                  {creatingThread ? "Starting…" : "Start chat"}
                </button>
              </div>
            ) : historyLoading ? (
              <p className="text-sm text-cast-iron/60">Loading conversation…</p>
            ) : historyError && transcript.length === 0 ? (
              <p className="text-sm text-chili">{historyError}</p>
            ) : transcript.length === 0 ? (
              <p className="text-sm text-cast-iron/60">
                Ask Chef about recipes, substitutions, or a day plan — every recipe it names is
                safety-checked against your profile before it's mentioned.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {transcript.map((row) => (
                  <ChatMessage key={row.id} row={row} onViewRecipe={setViewRecipeId} />
                ))}
                {isStreaming && (
                  <p aria-hidden="true" className="text-xs italic text-cast-iron/50">
                    Chef is thinking…
                  </p>
                )}
              </div>
            )}

            {streamError && (
              <div className="mt-3 rounded-md border border-chili bg-chili/5 px-3 py-2 text-sm text-chili">
                {streamError}
              </div>
            )}
          </div>

          {!showProfileGate && activeThreadId && (
            <form onSubmit={handleSend} className="flex gap-2 border-t border-sage-line p-3">
              <label className="sr-only" htmlFor="chat-message-input">
                Message Chef
              </label>
              <input
                id="chat-message-input"
                type="text"
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                disabled={isStreaming}
                placeholder="Ask Chef anything about your meals…"
                className="flex-1 rounded-md border border-sage-line bg-white px-3 py-2 text-sm text-cast-iron focus:border-basil disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={isStreaming || inputValue.trim().length === 0}
                className="rounded-md bg-cast-iron px-4 py-2 text-sm font-semibold text-porcelain disabled:opacity-50"
              >
                {isStreaming ? "Sending…" : "Send"}
              </button>
            </form>
          )}
        </div>
      </div>

      {viewRecipeId && (
        <RecipeDetailModal recipeId={viewRecipeId} onClose={() => setViewRecipeId(null)} />
      )}
    </div>
  );
}
