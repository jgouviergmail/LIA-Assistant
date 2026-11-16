'use client';

/**
 * The reminders that have not fired yet.
 *
 * Read-only, deliberately: this lists what is still COMING. Editing a reminder
 * belongs to its settings screen, cancelling to the briefing card behind its
 * own confirmation — duplicating that here would mean two dialogs for one
 * deletion — and postponing to the reminder that RANG, from its bubble or its
 * notification (ADR-268 amendment 2026-11-16): a reminder still pending has
 * nothing to postpone yet.
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
