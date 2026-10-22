'use client';
import { createElement, useCallback, useEffect, useRef } from 'react';
import { MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { SmsReceivedSignal } from '@/lib/sms/notification';
import type { SmsMessage } from '@/types/sms';

/** How long a notice waits for its message before announcing the arrival alone. */
export const SMS_NOTICE_READ_TIMEOUT_MS = 4000;
/** A notice that shows the message stays long enough to read it. */
export const SMS_NOTICE_DURATION_MS = 8000;

interface NoticeScope {
  ids: Set<string>;
  signal: AbortSignal;
}

/** The announced message through the session-only archive read, or null when unreadable. */
async function readNoticeMessage(
  messageId: string,
  signal: AbortSignal
): Promise<SmsMessage | null> {
  try {
    return await apiClient.get<SmsMessage>(`/sms/${encodeURIComponent(messageId)}`, {
      signal,
      timeout: SMS_NOTICE_READ_TIMEOUT_MS,
    });
  } catch (error) {
    // Erased meanwhile, archive closed, network: the arrival is still announced.
    logger.debug('sms_notice_read_failed', {
      component: 'useSmsReceivedToast',
      errorType: error instanceof Error ? error.name : typeof error,
    });
    return null;
  }
}

/**
 * The received-SMS notice: its sender as the bold title, its text below.
 *
 * The signal carries no sender and no body (ADR-357 keeps the wire
 * content-free); both are read through the session-only archive read when the
 * signal arrives, and a failed read still announces a new SMS. An account
 * change or an unmount aborts the read and dismisses what was shown, and a
 * stale account callback can neither show nor navigate.
 */
export function useSmsReceivedToast(ownerId: string | undefined) {
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const { isCurrent, lifetime } = useApplicationAccountLifetime(ownerId);
  const notices = useRef<NoticeScope | null>(null);
  useEffect(() => {
    const ids = new Set<string>();
    const controller = new AbortController();
    notices.current = { ids, signal: controller.signal };
    return () => {
      controller.abort();
      for (const id of ids) toast.dismiss(id);
      ids.clear();
    };
  }, [lifetime]);
  return useCallback(
    (signal: SmsReceivedSignal) => {
      const scope = notices.current;
      if (!scope || !isCurrent() || signal.user_id !== ownerId) return;
      const id = `sms:${signal.occurrence_id}`;
      scope.ids.add(id);
      void readNoticeMessage(signal.message_id, scope.signal).then(message => {
        if (scope.signal.aborted || !scope.ids.has(id) || !isCurrent()) return;
        toast.info(message ? message.display_name : t('sms.new_received'), {
          id,
          icon: createElement(MessageSquareText, { 'aria-hidden': true }),
          // The SMS is plain text: rendered as children, never as Markdown.
          description: message
            ? createElement(
                'span',
                { dir: 'auto', className: 'line-clamp-4 whitespace-pre-line' },
                message.body
              )
            : undefined,
          duration: message ? SMS_NOTICE_DURATION_MS : undefined,
          onAutoClose: () => {
            scope.ids.delete(id);
          },
          onDismiss: () => {
            scope.ids.delete(id);
          },
          action: {
            label: t('sms.archive'),
            onClick: () => {
              if (isCurrent())
                router.push(`/dashboard/sms?message=${encodeURIComponent(signal.message_id)}`);
            },
          },
        });
      });
    },
    [isCurrent, ownerId, t, router]
  );
}
