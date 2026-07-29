/**
 * Client-side Chef chat thread list (ROADMAP.md Step 4.3's own design call:
 * "thread list in a sidebar (localStorage of thread ids)"). The backend has
 * no "list my threads" endpoint -- only `POST /chat` (create) and `GET
 * /chat/{thread_id}` (fetch-by-id), see `app.api.routes_chat`'s module
 * docstring -- so this browser's localStorage is the only record of which
 * threads exist to switch between. Same posture as `lib/profile.ts`'s form
 * persistence: non-secret UX convenience state only; a full disk or
 * disabled storage degrades to "no remembered threads", never a hard
 * failure.
 */
export interface ChatThreadSummary {
  threadId: string;
  /** Mirrors `ChatThreadStatusResponse.title` once the server sets it
   * (`ChatThreadRepository.set_title_if_unset`, from the thread's first
   * message) -- `null` until then; the sidebar renders a "New chat"
   * placeholder for a `null` title. */
  title: string | null;
  createdAt: string;
}

export const CHAT_THREADS_STORAGE_KEY = "macrochef.chatThreads.v1";

export function loadChatThreads(): ChatThreadSummary[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(CHAT_THREADS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as ChatThreadSummary[]) : [];
  } catch {
    return [];
  }
}

function saveChatThreads(threads: ChatThreadSummary[]): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(CHAT_THREADS_STORAGE_KEY, JSON.stringify(threads));
  } catch {
    // Non-secret UX convenience state only -- see module docstring.
  }
}

/** Prepends a newly created thread (most-recent-first, the sidebar's
 * display order) and persists the updated list. */
export function addChatThread(
  threads: ChatThreadSummary[],
  thread: ChatThreadSummary,
): ChatThreadSummary[] {
  const next = [thread, ...threads.filter((existing) => existing.threadId !== thread.threadId)];
  saveChatThreads(next);
  return next;
}

/** Updates one thread's title in place (once the server sets it after the
 * thread's first message) without reordering the list. */
export function updateChatThreadTitle(
  threads: ChatThreadSummary[],
  threadId: string,
  title: string,
): ChatThreadSummary[] {
  const next = threads.map((thread) =>
    thread.threadId === threadId ? { ...thread, title } : thread,
  );
  saveChatThreads(next);
  return next;
}

/** Drops a thread id this browser no longer has server-side access to (a
 * 404 from `GET /chat/{thread_id}` -- see `api/endpoints.ts`'s
 * `getChatThread` docstring for why that can never be distinguished from
 * "never existed" here). */
export function removeChatThread(
  threads: ChatThreadSummary[],
  threadId: string,
): ChatThreadSummary[] {
  const next = threads.filter((thread) => thread.threadId !== threadId);
  saveChatThreads(next);
  return next;
}
