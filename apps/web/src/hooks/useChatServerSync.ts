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

import { useReminderSnoozeAction } from '@/hooks/useReminderSnoozeAction';
import { useSmsReceivedToast } from '@/hooks/useSmsReceivedToast';
import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import type { ConversationPage, ConversationTotals } from '@/hooks/useConversation';
import { useConversationSync } from '@/hooks/useConversationSync';
import {
  useNotifications,
  type ConversationSignal,
  type Notification,
} from '@/hooks/useNotifications';
import { notificationElsewhere } from '@/lib/notification-discussion';
import { NOTIFICATION_PREVIEW_MAX_LENGTH, toPlainPreview } from '@/lib/notification-preview';
import type { Message } from '@/types/chat';
import type { ConversationSelection } from '@/types/conversation';
import { conversationScopeKey } from '@/lib/conversation-selection';
import type { ReminderSnoozeOffer } from '@/lib/reminder-firing';

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
  if (metadata?.type === 'proactive_discussion')
    return { message: '💬 LIA', className: '!bg-primary/10 !border-primary/25' };
  const isPeer =
    typeof metadata?.type === 'string' && (metadata.type as string).startsWith('proactive_peer');
  const peerName = (metadata?.sender_name ?? metadata?.peer_name) as string | undefined;
  const topic = metadata?.interest_topic as string | undefined;
  return {
    message: isPeer ? `🤝 ${peerName || 'Info'}` : topic ? `💡 ${topic}` : '💡 Info',
    className: isPeer ? '!bg-primary/10 !border-primary/25' : undefined,
  };
}

/**
 * Whether a thread signal is about the discussion this view shows. The
 * account's channel carries every discussion's signals, and another
 * discussion's never touches this thread.
 *
 * @param signalId - The discussion the signal names.
 * @param selection - The view's coordinates, when it was opened with some.
 * @param knownId - The shown discussion's id, when its record is known.
 * @param isMain - The view shows Main.
 * @returns True when the thread on screen is the one the signal names.
 */
function concernsShownThread(
  signalId: string,
  selection: ConversationSelection | undefined,
  knownId: string | undefined,
  isMain: boolean
): boolean {
  if (selection) return signalId === selection.conversation_id;
  // Without coordinates only a view of Main listens; until its record is
  // known it cannot tell the discussions apart and takes every signal.
  if (!isMain) return false;
  return knownId === undefined || signalId === knownId;
}

export interface UseChatServerSyncOptions {
  selection?: ConversationSelection;
  /**
   * The discussion on screen, when its record is known although the view was
   * opened without coordinates (the first view of Main). The account's channel
   * carries every discussion's signals: without it, that view cannot tell its
   * own reset from a neighbour's.
   */
  conversationId?: string;
  isMain?: boolean;
  onCatalogueChange?: () => void;
  onSelectedReset?: () => void;
  onMetadataChange?: () => void;
  /**
   * What the person calls a discussion of the account (Main's label, an
   * annex's title), or `null` when the catalogue on hand does not hold it.
   */
  discussionTitle?: (id: string) => string | null;
  /**
   * Opens another discussion through the switcher's door (`null`: Main);
   * absent while leaving would cancel the turn on screen (`discussion-leave`).
   */
  openDiscussion?: (id: string | null) => void;
  refreshUsage?: () => Promise<void>;
  /** The signed-in account; its zone dates a postponed reminder's verdict. */
  owner: { readonly id: string; readonly timezone?: string | null } | null;
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
  /** ADR-384: the shown thread changed elsewhere — a waiting message may have left. */
  onThreadSignal?: () => void;
}

const ignoreThreadSignal = (): void => undefined;

/** A reminder's toast that offers a « later » stays long enough to be pressed. */
const REMINDER_TOAST_WITH_ACTION_MS = 10_000;

export function useChatServerSync(options: UseChatServerSyncOptions): void {
  const {
    owner,
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
    selection,
    conversationId,
    isMain = true,
    onCatalogueChange,
    onSelectedReset,
    onMetadataChange,
    discussionTitle,
    openDiscussion,
    refreshUsage,
    onThreadSignal = ignoreThreadSignal,
  } = options;
  const { t } = useTranslation();
  // What the screen shows, read when a notification LANDS (and again when its
  // toast is clicked), never captured when a handler is made: a discussion
  // switched, a turn starting, a title renamed or a parent's new callback must
  // never change a handler's identity. Each new identity made useNotifications
  // close and reopen its stream — measured 2026-11-15 in a production bundle:
  // five times while the chat loaded, two or three when a turn started — and
  // an event published in between reached a closed connection and was lost.
  const screenRef = useRef({
    discussionTitle,
    openDiscussion,
    selection,
    conversationId,
    isMain,
    t,
    onCatalogueChange,
    onNotification,
  });
  useEffect(() => {
    screenRef.current = {
      discussionTitle,
      openDiscussion,
      selection,
      conversationId,
      isMain,
      t,
      onCatalogueChange,
      onNotification,
    };
  });

  const onSmsReceived = useSmsReceivedToast(owner?.id);
  const reminderSnoozeAction = useReminderSnoozeAction(owner?.timezone ?? undefined);
  const readSyncedPage = useCallback(async () => {
    const page = await readNewestPage();
    void hydratePendingHitl();
    void refreshUsage?.();
    return page;
  }, [readNewestPage, hydratePendingHitl, refreshUsage]);

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
    ownerId: owner?.id,
    scopeKey: conversationScopeKey(owner?.id, selection),
    enabled: signedIn && apiAvailable,
    blocked: isTyping || historyView || isLoadingOlder,
    messages,
    readNewestPage: readSyncedPage,
    mergeServerPage,
    onPageReplaced: syncReplacedPage,
    onReset: syncReset,
  });

  const syncNotification = useCallback(
    (metadata?: Record<string, unknown>) => {
      const screen = screenRef.current;
      screen.onCatalogueChange?.();
      const target = metadata?.conversation_id;
      if (typeof target === 'string' ? target === screen.selection?.conversation_id : screen.isMain)
        requestSync('notification');
    },
    [requestSync]
  );

  /**
   * Where a notification landed, when it is not the discussion on screen
   * (ADR-378 amendment 2026-11-14): the toast names it before its preview —
   * Main included, for one naming no discussion seen from an annex — and
   * offers to open it where leaving is allowed when the toast shows.
   */
  const placed = useCallback(
    (metadata: Record<string, unknown> | undefined, description: string | undefined) => {
      const screen = screenRef.current;
      const where = notificationElsewhere(metadata, {
        id: screen.selection?.conversation_id ?? screen.conversationId ?? null,
        isMain: screen.isMain,
      });
      if (where === null) return { description };
      const title =
        where.kind === 'main'
          ? screen.t('chat.discussions.main')
          : (screen.discussionTitle?.(where.id) ?? null);
      const place =
        title === null
          ? screen.t('chat.discussions.notification_elsewhere_untitled')
          : screen.t('chat.discussions.notification_elsewhere', { title });
      const target = where.kind === 'main' ? null : where.id;
      return {
        description: description ? `${place} · ${description}` : place,
        action: screen.openDiscussion
          ? {
              label: screen.t('chat.discussions.notification_open'),
              // Leaving is asked again at the click: a turn may have started.
              onClick: () => screenRef.current.openDiscussion?.(target),
            }
          : undefined,
      };
    },
    []
  );

  const handleReminder = useCallback(
    (content: string, _reminderId: string, offer?: ReminderSnoozeOffer) => {
      // Flattened for the toast only: the thread renders the archived row,
      // in Main — named when an annex is on screen. There, the toast opens
      // Main, whose bubble offers every « later »; on Main itself it offers
      // the short one (ADR-268 amendment 2026-11-16), and stays long enough
      // to be pressed.
      const where = placed(undefined, undefined);
      const snooze = where.action ? undefined : reminderSnoozeAction(offer);
      toast.info(toPlainPreview(content), {
        duration: snooze ? REMINDER_TOAST_WITH_ACTION_MS : 5000,
        ...where,
        ...(snooze ? { action: snooze } : {}),
      });
      syncNotification();
    },
    [syncNotification, placed, reminderSnoozeAction]
  );

  const handleProactiveNotification = useCallback(
    (content: string, _targetId: string, metadata?: Record<string, unknown>) => {
      if (metadata?.sensitive_in_app_only === true) {
        syncNotification(metadata);
        return;
      }
      if (metadata?.event === 'live_relay') {
        // The relayed turn of a DIRECT live session settled (ADR-301): its rows
        // and the rewritten closing card are in the thread.
        toast.info(content, { duration: 5000, ...placed(metadata, undefined) });
      } else {
        const presentation = proactiveToastPresentation(metadata);
        toast.info(presentation.message, {
          duration: 5000,
          className: presentation.className,
          ...placed(metadata, toPlainPreview(content, NOTIFICATION_PREVIEW_MAX_LENGTH)),
        });
      }
      syncNotification(metadata);
    },
    [syncNotification, placed]
  );

  // A routine's event carries a truncated preview for the toast; the full
  // result is the row the run archived — in the annex a run asked there
  // answered in, which the event then names.
  const handleScheduledAction = useCallback(
    (content: string, _actionId: string, title: string, metadata?: Record<string, unknown>) => {
      toast.info(title, {
        duration: 5000,
        ...placed(metadata, toPlainPreview(content, NOTIFICATION_PREVIEW_MAX_LENGTH)),
      });
      syncNotification(metadata);
    },
    [syncNotification, placed]
  );

  const handleConversationEvent = useCallback(
    (signal: ConversationSignal) => {
      onCatalogueChange?.();
      if (signal.type === 'conversation_metadata') {
        onMetadataChange?.();
        if (signal.conversation_id === selection?.conversation_id) onSelectedReset?.();
        return;
      }
      if (!concernsShownThread(signal.conversation_id, selection, conversationId, isMain)) return;
      if (signal.type === 'conversation_reset') {
        // A notification can arrive late: the authenticated catalogue alone
        // decides whether this generation was retired. Never clear a newer one.
        if (selection) onSelectedReset?.();
        else requestReset();
      } else {
        requestSync('signal');
        onThreadSignal();
      }
    },
    [
      onThreadSignal,
      requestReset,
      requestSync,
      selection,
      conversationId,
      isMain,
      onCatalogueChange,
      onSelectedReset,
      onMetadataChange,
    ]
  );
  // Pub/Sub keeps nothing: a stream that was down missed what was published.
  const handleReconnected = useCallback(() => {
    requestSync('reconnected');
    onSelectedReset?.();
  }, [requestSync, onSelectedReset]);

  const forwardNotification = useCallback(
    (notification: Notification) => screenRef.current.onNotification(notification),
    []
  );

  // Admin broadcasts are handled by BroadcastProvider (its own listeners).
  useNotifications({
    ownerId: owner?.id,
    onSmsReceived,
    enableSSE: true,
    enableFCM: true,
    isAuthenticated: signedIn && !authLoading,
    onNotification: forwardNotification,
    onReminder: handleReminder,
    onProactiveNotification: handleProactiveNotification,
    onScheduledAction: handleScheduledAction,
    onConversationEvent: handleConversationEvent,
    onReconnected: handleReconnected,
  });
}
