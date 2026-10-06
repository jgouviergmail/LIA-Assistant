'use client';

/**
 * What keeps the chat in step with what happens elsewhere (ADR-320).
 *
 * The person's real-time channel carries two kinds of events: notifications
 * they are told about (a reminder, a proactive message, a routine's result)
 * and the thread's own sync signals. Both end the same way — the newest page
 * MERGED into the thread (`lib/chat-sync.ts`) — and only a notification adds a
 * toast. A notification's message is never built here as a bubble: it came
 * back a second time at the next read of the history, under the id of the row
 * the server archived.
 *
 * Extracted from the chat page, whose render function sits under a
 * shrink-only complexity ratchet.
 */

import { useCallback } from 'react';
import { toast } from 'sonner';

import type { ConversationPage, ConversationTotals } from '@/hooks/useConversation';
import { useConversationSync } from '@/hooks/useConversationSync';
import {
  useNotifications,
  type ConversationSignal,
  type Notification,
} from '@/hooks/useNotifications';
import { NOTIFICATION_PREVIEW_MAX_LENGTH, toPlainPreview } from '@/lib/notification-preview';
import type { Message } from '@/types/chat';

/**
 * Toast title + tint for a proactive push.
 * Peer notifications (Lot 7) reuse their chat-bubble tint so they read as
 * "peer" at a glance; interests title with their topic; the rest stays generic.
 * NOTE: decision_reason is internal English LLM reasoning — NOT user-facing.
 *
 * @param metadata - The notification's metadata.
 * @returns The toast's title and class.
 */
export function proactiveToastPresentation(metadata?: Record<string, unknown>): {
  message: string;
  className: string | undefined;
} {
  const isPeer =
    typeof metadata?.type === 'string' && (metadata.type as string).startsWith('proactive_peer');
  const peerName = (metadata?.sender_name ?? metadata?.peer_name) as string | undefined;
  const topic = metadata?.interest_topic as string | undefined;
  return {
    message: isPeer ? `🤝 ${peerName || 'Info'}` : topic ? `💡 ${topic}` : '💡 Info',
    className: isPeer ? '!bg-primary/10 !border-primary/25' : undefined,
  };
}

export interface UseChatServerSyncOptions {
  /** An account is signed in. */
  signedIn: boolean;
  /** Authentication is still resolving: the channel waits (no 401 loop). */
  authLoading: boolean;
  /** The API answers. */
  apiAvailable: boolean;
  /** A turn streams: the thread must not be touched. */
  isTyping: boolean;
  /** A past page of history is on screen (QW-2). */
  historyView: boolean;
  /** Older messages are loading. */
  isLoadingOlder: boolean;
  /** The thread on screen. */
  messages: Message[];
  /** The newest page; throws on a transport failure. */
  readNewestPage: () => Promise<ConversationPage>;
  /** Merge a page into the thread. */
  mergeServerPage: (messages: Message[]) => void;
  /** Empty the thread. */
  clearMessages: () => void;
  /** The API totals shown in the header. */
  setApiTotals: (totals: ConversationTotals | null) => void;
  /** Scroll-up pagination state. */
  setHasMoreOlder: (hasMore: boolean) => void;
  setOldestCursor: (cursor: string | null) => void;
  /** Every notification (the expressive eyes' ping). */
  onNotification: (notification: Notification) => void;
  /** Reconcile the pending approval alongside messages received elsewhere. */
  hydratePendingHitl: () => Promise<void>;
}

export function useChatServerSync(options: UseChatServerSyncOptions): void {
  const {
    signedIn,
    authLoading,
    apiAvailable,
    isTyping,
    historyView,
    isLoadingOlder,
    messages,
    readNewestPage,
    mergeServerPage,
    clearMessages,
    setApiTotals,
    setHasMoreOlder,
    setOldestCursor,
    onNotification,
    hydratePendingHitl,
  } = options;

  const readSyncedPage = useCallback(async () => {
    const page = await readNewestPage();
    void hydratePendingHitl();
    return page;
  }, [readNewestPage, hydratePendingHitl]);

  const syncReplacedPage = useCallback(
    (page: ConversationPage) => {
      // More than a page arrived while away: scroll-up restarts from the page.
      setHasMoreOlder(page.hasMore);
      setOldestCursor(page.nextCursor);
    },
    [setHasMoreOlder, setOldestCursor]
  );
  const syncReset = useCallback(() => {
    // The conversation was emptied elsewhere (another tab, another device).
    clearMessages();
    setApiTotals(null);
    setHasMoreOlder(false);
    setOldestCursor(null);
  }, [clearMessages, setApiTotals, setHasMoreOlder, setOldestCursor]);

  // Nothing is touched while a turn streams, a past page is shown or older
  // messages load: what is asked meanwhile runs once the thread is free.
  const { requestSync, requestReset } = useConversationSync({
    enabled: signedIn && apiAvailable,
    blocked: isTyping || historyView || isLoadingOlder,
    messages,
    readNewestPage: readSyncedPage,
    mergeServerPage,
    onPageReplaced: syncReplacedPage,
    onReset: syncReset,
  });

  const handleReminder = useCallback(
    (content: string) => {
      // Flattened for the toast only: the thread renders the archived row.
      toast.info(toPlainPreview(content), { duration: 5000 });
      requestSync('notification');
    },
    [requestSync]
  );

  const handleProactiveNotification = useCallback(
    (content: string, _targetId: string, metadata?: Record<string, unknown>) => {
      if (metadata?.event === 'live_relay') {
        // The relayed turn of a DIRECT live session settled (ADR-301): its rows
        // and the rewritten closing card are in the thread.
        toast.info(content, { duration: 5000 });
      } else {
        const presentation = proactiveToastPresentation(metadata);
        toast.info(presentation.message, {
          duration: 5000,
          description: toPlainPreview(content, NOTIFICATION_PREVIEW_MAX_LENGTH),
          className: presentation.className,
        });
      }
      requestSync('notification');
    },
    [requestSync]
  );

  // A routine's event carries a truncated preview for the toast; the full
  // result is the row the run archived.
  const handleScheduledAction = useCallback(
    (content: string, _actionId: string, title: string) => {
      toast.info(title, {
        duration: 5000,
        description: toPlainPreview(content, NOTIFICATION_PREVIEW_MAX_LENGTH),
      });
      requestSync('notification');
    },
    [requestSync]
  );

  const handleConversationEvent = useCallback(
    (signal: ConversationSignal) => {
      if (signal === 'conversation_reset') requestReset();
      else requestSync('signal');
    },
    [requestReset, requestSync]
  );
  // Pub/Sub keeps nothing: a stream that was down missed what was published.
  const handleReconnected = useCallback(() => requestSync('reconnected'), [requestSync]);

  // Admin broadcasts are handled by BroadcastProvider (its own listeners).
  useNotifications({
    enableSSE: true,
    enableFCM: true,
    isAuthenticated: signedIn && !authLoading,
    onNotification,
    onReminder: handleReminder,
    onProactiveNotification: handleProactiveNotification,
    onScheduledAction: handleScheduledAction,
    onConversationEvent: handleConversationEvent,
    onReconnected: handleReconnected,
  });
}
