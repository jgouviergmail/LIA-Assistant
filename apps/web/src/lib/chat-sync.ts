/**
 * Keeping the chat in step with the server without reloading it (ADR-320).
 *
 * Messages land in a person's conversation from many places — another tab, a
 * Telegram turn, a routine, a reminder, a voice relay. The server says so on
 * the person's real-time channel once each change is committed, and the tab
 * also asks on its own when it may have missed something (back to the
 * foreground, back online, stream reconnected). Each ask becomes, at most, one
 * read of the newest page MERGED into the thread (`lib/chat-merge.ts`) — never
 * a reload.
 *
 * Three rules, each a way an earlier version disturbed the reader:
 *
 * - **Asks coalesce.** Ten signals during one read make one more read after
 *   it, not ten.
 * - **The thread is never touched while it is busy**: a turn streaming, a past
 *   page of history on screen, older messages loading — the ask waits and runs
 *   once the thread is free ({@link ChatSyncController.resume}). A reader in
 *   the middle of a gesture (a text selection, an open menu) is waited for too,
 *   by looking again a little later.
 * - **A failed read is not an empty conversation**: nothing is merged, nothing
 *   is retried in a loop — the next ask (a signal, a return, a reconnection)
 *   reads again. A reset is applied only when the server announced one.
 *
 * A plain class, tested without React; `useConversationSync` wires it.
 */

import { logger } from '@/lib/logger';
import { mergeServerPage } from '@/lib/chat-merge';
import type { Message } from '@/types/chat';

/** How long an ask the reader's gesture deferred waits before looking again. */
export const SYNC_RETRY_WHILE_BUSY_MS = 1500;

/** What the controller reads and writes, injected so it is testable alone. */
export interface ChatSyncDeps<Page extends { messages: Message[] }> {
  /** Whether syncing makes sense at all (signed in, API reachable). */
  enabled: () => boolean;
  /** Whether the thread must not be touched now (streaming, past page, paginating). */
  blocked: () => boolean;
  /** Whether the reader is in the middle of a gesture a re-render could disturb. */
  readerBusy: () => boolean;
  /** The thread on screen, as last rendered. */
  messages: () => Message[];
  /** The newest page; THROWS on a transport failure. */
  readNewestPage: () => Promise<Page>;
  /** Merge a page into the thread (the reducer's `MERGE_SERVER_PAGE`). */
  mergeServerPage: (messages: Message[]) => void;
  /** The page lay beyond the thread: pagination restarts from it. */
  onPageReplaced: (page: Page) => void;
  /** Empty the thread: the server announced a reset. */
  onReset: () => void;
  setTimer: (callback: () => void, ms: number) => unknown;
  clearTimer: (handle: unknown) => void;
}

/** Why a sync was asked for — logged, never branched on. */
export type SyncReason = 'signal' | 'visible' | 'online' | 'reconnected' | 'notification';

/** Coalesces, defers and applies the syncs of one chat thread. */
export class ChatSyncController<Page extends { messages: Message[] }> {
  private wantsSync = false;
  private wantsReset = false;
  private inFlight = false;
  private retryHandle: unknown = null;
  private disposed = false;

  constructor(private readonly deps: ChatSyncDeps<Page>) {}

  /** Ask for the newest page to be merged. */
  request(reason: SyncReason): void {
    logger.debug('conversation_sync_requested', { component: 'ChatSync', reason });
    this.wantsSync = true;
    void this.run();
  }

  /** The server emptied the conversation: empty the thread once it is free. */
  requestReset(): void {
    this.wantsReset = true;
    void this.run();
  }

  /** The thread became free (a turn ended, the reader returned to the present). */
  resume(): void {
    if (this.wantsSync || this.wantsReset) void this.run();
  }

  /** Stop for good (the chat unmounted): nothing already asked will run. */
  dispose(): void {
    this.disposed = true;
    this.wantsSync = false;
    this.wantsReset = false;
    if (this.retryHandle !== null) this.deps.clearTimer(this.retryHandle);
    this.retryHandle = null;
  }

  private mayRun(): boolean {
    if (this.disposed || this.inFlight || !this.deps.enabled()) return false;
    // `resume()` runs again once the thread is free.
    if (this.deps.blocked()) return false;
    if (this.deps.readerBusy()) {
      this.lookAgainLater();
      return false;
    }
    return true;
  }

  private lookAgainLater(): void {
    if (this.retryHandle !== null) return;
    this.retryHandle = this.deps.setTimer(() => {
      this.retryHandle = null;
      void this.run();
    }, SYNC_RETRY_WHILE_BUSY_MS);
  }

  private async run(): Promise<void> {
    if (!this.mayRun()) return;
    if (this.wantsReset) {
      this.wantsReset = false;
      this.deps.onReset();
    }
    if (!this.wantsSync) return;
    this.wantsSync = false;
    this.inFlight = true;
    try {
      this.apply(await this.deps.readNewestPage());
    } catch (error) {
      logger.warn('conversation_sync_failed', {
        component: 'ChatSync',
        error: error instanceof Error ? error.name : 'unknown',
      });
    } finally {
      this.inFlight = false;
    }
    // What was asked during the read runs now (it may wait for the thread).
    if (!this.disposed && (this.wantsSync || this.wantsReset)) void this.run();
  }

  private apply(page: Page): void {
    if (this.disposed) return;
    if (this.deps.blocked()) {
      // A turn started during the read: its end will bring this page again.
      this.wantsSync = true;
      return;
    }
    const { gap } = mergeServerPage(this.deps.messages(), page.messages);
    this.deps.mergeServerPage(page.messages);
    if (gap) this.deps.onPageReplaced(page);
  }
}
