'use client';

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { useApiMutation } from './useApiMutation';
import {
  buildMailWatch,
  canWatch,
  existingWatchFor,
  watchQueryFor,
  type MailWatchPayload,
  type MailWatchSource,
} from '@/lib/mail-watch';
import type { ScheduledAction } from './useScheduledActions';

/** What `GET /scheduled-actions` answers. */
interface ScheduledActionList {
  scheduled_actions: ScheduledAction[];
  total: number;
}

/**
 * Post a mail watch from a briefing card (ADR-281, lot 5).
 *
 * Deliberately NOT `useScheduledActions()`: that hook polls the listing every
 * thirty seconds, and the dashboard has no listing to show — mounting it here
 * would add a permanent request to a page that only ever WRITES one routine.
 * The listing is read ON CLICK instead, once, for one reason: to refuse a
 * duplicate.
 *
 * **Asking before writing is the point.** Two mails from the same person are
 * ordinary, and clicking the chip on both would create two identical watches,
 * each holding one of the account's twenty routine slots and each notifying —
 * so one awaited reply would be announced twice. Being told twice is exactly
 * what a proactive assistant must not do.
 *
 * The SHAPE comes from `lib/mail-watch`; this hook carries it to the API and
 * says what happened. A failure is told, never swallowed: the person pressed a
 * button, and silence reads as success.
 */
export function useMailWatch(onCreated?: () => void) {
  const { t } = useTranslation();
  const { mutate, loading } = useApiMutation<MailWatchPayload, ScheduledAction>({
    method: 'POST',
    componentName: 'MailWatch',
  });

  const watch = useCallback(
    async (mail: MailWatchSource, sender: string) => {
      if (!canWatch(mail)) return;
      try {
        const existing = await apiClient.get<ScheduledActionList>('/scheduled-actions');
        if (existingWatchFor(existing?.scheduled_actions ?? [], watchQueryFor(mail))) {
          // Not an error: the person already asked, and saying so is the
          // answer. Creating a second one would notify them twice.
          toast.info(t('dashboard.briefing.watch.already', { sender }));
          return;
        }
        const created = await mutate(
          '/scheduled-actions',
          buildMailWatch({
            mail,
            title: t('dashboard.briefing.watch.title', { sender }),
            actionPrompt: t('dashboard.briefing.watch.prompt', { sender }),
          })
        );
        if (!created) throw new Error('mail_watch_not_created');
        toast.success(t('dashboard.briefing.watch.created', { sender }));
        onCreated?.();
      } catch {
        toast.error(t('dashboard.briefing.watch.failed'));
      }
    },
    [mutate, onCreated, t]
  );

  return { watch, loading };
}
