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
  return (
    <ul className="divide-y divide-border" role="list">
      {reminders.map(reminder => (
        <li key={reminder.id} className="min-w-0 py-4 first:pt-0 last:pb-0">
          <div className="min-w-0 flex-1">
            <p className="break-words whitespace-pre-line text-sm leading-relaxed text-foreground/90">
              {reminder.content}
            </p>
            <time
              dateTime={reminder.trigger_at}
              className="mt-1 block text-xs font-bold tabular-nums leading-relaxed text-muted-foreground"
            >
              {formatInstant(reminder.trigger_at, locale)}
            </time>
          </div>
        </li>
      ))}
    </ul>
  );
}
