'use client';

/**
 * useWaitingComposer — what the chat does with words written while LIA works (ADR-384).
 *
 * Composes the discussion's waiting message with the composer and the stream:
 *
 * - `takes(words, extras)` decides whether a send waits (`composerRoute`) and,
 *   when it does, keeps the words behind the run the page streams;
 * - `onBusyRefusal` turns a plain send a busy account refused into a waiting
 *   message, and goes on watching the running answer when it is this discussion's;
 * - the bubble's actions report a refusal in the server's own sentence and give
 *   refused words back to the composer, never dropping them;
 * - the message is read again when the page's own turn ends, and when the
 *   thread changed elsewhere (it may have left: the page then joins its run);
 * - « Add to the answer in progress » hands it to the running answer as a note
 *   (ADR-385); refused, the reason is said and the message read again, since the
 *   offer it came from was already stale.
 */

import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import type { WaitingMessageBubbleProps } from '@/components/chat/WaitingMessageBubble';
import type { BusyRefusalHandler } from '@/hooks/useChat';
import { useLiaGender } from '@/hooks/useLiaGender';
import { useWaitingMessage, type WaitingRendering } from '@/hooks/useWaitingMessage';
import { getApiErrorDetail, getApiErrorStatus } from '@/lib/api-error';
import { isSelectedRun } from '@/lib/conversation-selection';
import { composerRoute, isQueueable, type SendExtras } from '@/lib/waiting-message';
import type { ConversationSelection } from '@/types/conversation';

/** The refusals whose detail the API wrote for the reader (a conflict, a bound). */
const SPOKEN_REFUSALS: ReadonlySet<number> = new Set([409, 422]);

export interface UseWaitingComposerArgs {
  selection: ConversationSelection | undefined;
  enabled: boolean;
  /** The page streams its own answer. */
  busy: boolean;
  /** A question waits for the person's answer in this discussion. */
  questionPending: boolean;
  /** The run the page streams. */
  runStreamId: () => string | null;
  /** Join a run that is sending the person's words. */
  joinRun: (streamId: string) => void;
  /** Look for a running answer to join (after the thread changed elsewhere). */
  joinRunningAnswer: () => void;
  /** Put refused words back in the composer. */
  restoreText: (text: string) => void;
}

export interface UseWaitingComposerReturn {
  /** True when the send waits (the words were handed to the server). */
  takes: (words: string, extras: SendExtras) => boolean;
  /** For `useChat`: a plain send a busy account refused waits instead. */
  onBusyRefusal: BusyRefusalHandler;
  /** The bubble's props, or null when nothing waits. */
  bubble: WaitingMessageBubbleProps | null;
  /** The thread changed elsewhere: read again, and join what may now run. */
  onThreadSignal: () => void;
}

export function useWaitingComposer(args: UseWaitingComposerArgs): UseWaitingComposerReturn {
  const { selection, enabled, busy, questionPending, runStreamId } = args;
  const { joinRun, joinRunningAnswer, restoreText } = args;
  const { t } = useTranslation();
  const { isMale } = useLiaGender();
  const waiting = useWaitingMessage(selection, enabled);
  const { message, refresh } = waiting;

  const say = useCallback(
    (error: unknown) => {
      const status = getApiErrorStatus(error);
      const spoken = status !== undefined && SPOKEN_REFUSALS.has(status);
      toast.error((spoken && getApiErrorDetail(error)) || t('errors.generic'));
    },
    [t]
  );

  const keep = useCallback(
    async (words: string, behindStreamId: string | null) => {
      const rendering: WaitingRendering = {
        lia_gender: isMale ? 'male' : 'female',
        viewport_width: window.innerWidth,
      };
      try {
        const response = await waiting.queue(words, { behindStreamId, rendering });
        if (response?.departed && response.stream_id) joinRun(response.stream_id);
      } catch (error) {
        say(error);
        restoreText(words);
      }
    },
    [waiting, isMale, joinRun, restoreText, say]
  );

  const takes = useCallback(
    (words: string, extras: SendExtras) => {
      const route = composerRoute({
        busy,
        waiting: message !== null,
        questionPending,
        queueable: isQueueable(extras),
      });
      if (route === 'send') return false;
      void keep(words, busy ? runStreamId() : null);
      return true;
    },
    [busy, message, questionPending, runStreamId, keep]
  );

  const onBusyRefusal = useCallback<BusyRefusalHandler>(
    ({ content, activeRun }) => {
      toast.info(t('chat.waiting.queued_busy'));
      void keep(content, activeRun?.stream_id ?? null);
      if (activeRun?.stream_id && isSelectedRun(activeRun, selection)) joinRun(activeRun.stream_id);
      return true;
    },
    [keep, joinRun, selection, t]
  );

  // The page's own turn ended: what waited has left, is leaving, or is held.
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy && enabled) void refresh();
    wasBusy.current = busy;
  }, [busy, enabled, refresh]);

  const onThreadSignal = useCallback(() => {
    if (!enabled) return;
    void refresh();
    if (!busy) joinRunningAnswer();
  }, [enabled, busy, refresh, joinRunningAnswer]);

  const onEdit = useCallback(
    async (text: string) => {
      try {
        await waiting.edit(text);
        return true;
      } catch (error) {
        say(error);
        return false;
      }
    },
    [waiting, say]
  );

  const onWithdraw = useCallback(() => {
    waiting.withdraw().catch(say);
  }, [waiting, say]);

  const onSendNow = useCallback(() => {
    waiting
      .sendNow()
      .then(response => {
        if (response?.departed && response.stream_id) joinRun(response.stream_id);
      })
      .catch(say);
  }, [waiting, joinRun, say]);

  const onJoin = useCallback(() => {
    waiting.join().catch(error => {
      say(error);
      void refresh();
    });
  }, [waiting, say, refresh]);

  const bubble =
    message === null
      ? null
      : {
          message,
          questionPending,
          pending: waiting.pending,
          onEdit,
          onWithdraw,
          onSendNow,
          onJoin,
        };
  return { takes, onBusyRefusal, bubble, onThreadSignal };
}
