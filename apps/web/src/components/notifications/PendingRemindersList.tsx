'use client';

/**
 * The reminders that have not fired yet.
 *
 * Read-only, deliberately: a reminder is a temporary post-it, deleted the
 * moment it is notified, and the domain has no editing, snoozing or
 * acknowledging surface. The briefing card owns the one action there is —
 * cancelling — behind its own confirmation, and duplicating that here would
 * mean two dialogs for one deletion.
 *
 * Soonest first, which is the order the backend returns and the order a reader
 * scans a "what is coming" list.
 */

import { Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { formatInstant } from '@/lib/format-instant';

export interface PendingReminder {
  id: string;
  content: string;
  trigger_at: string;
}

export function PendingRemindersList({
  reminders,
  locale,
}: {
  reminders: readonly PendingReminder[];
  locale: string;
}) {
  const { t } = useTranslation();

  return (
    <ul className="space-y-2" role="list">
      {reminders.map(reminder => (
        <li
          key={reminder.id}
          className="flex items-start gap-2 rounded-lg border border-border/40 bg-card/40 px-3 py-2"
        >
          <Clock
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-foreground/90">{reminder.content}</p>
            <time
              dateTime={reminder.trigger_at}
              className="text-[11px] tabular-nums text-muted-foreground"
            >
              {t('notifications_hub.reminder_at', {
                when: formatInstant(reminder.trigger_at, locale),
              })}
            </time>
          </div>
        </li>
      ))}
    </ul>
  );
}
