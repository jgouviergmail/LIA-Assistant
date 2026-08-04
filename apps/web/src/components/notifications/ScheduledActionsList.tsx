'use client';

/**
 * Routines, and when each will next run.
 *
 * Read-only: creating, editing and deleting a routine belongs to the settings
 * studio, which this section links to. What the hub adds is the ONE thing that
 * page cannot show — the routines next to everything else LIA holds for the
 * reader.
 *
 * `schedule_display` comes formatted from the backend, in the reader's
 * language and timezone: reformatting it here would be a second authority on
 * when a routine runs, and the two would disagree the first time a rule
 * changed.
 *
 * A disabled routine still LISTS — hiding it would make "why did it not run?"
 * unanswerable — but says so, and shows no next run, because it has none.
 */

import { CalendarClock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { formatInstant } from '@/lib/format-instant';

export interface ScheduledActionRow {
  id: string;
  title: string;
  is_enabled: boolean;
  next_trigger_at: string | null;
  schedule_display: string;
}

export function ScheduledActionsList({
  actions,
  locale,
}: {
  actions: readonly ScheduledActionRow[];
  locale: string;
}) {
  const { t } = useTranslation();

  return (
    <ul className="space-y-2" role="list">
      {actions.map(action => (
        <li
          key={action.id}
          className="flex items-start gap-2 rounded-lg border border-border/40 bg-card/40 px-3 py-2"
        >
          <CalendarClock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="text-sm font-medium text-foreground/90">{action.title}</span>
              {!action.is_enabled && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {t('notifications_hub.routine_disabled')}
                </span>
              )}
            </p>
            <p className="text-[11px] text-muted-foreground">{action.schedule_display}</p>
            {action.is_enabled && (
              <p className="text-[11px] tabular-nums text-muted-foreground">
                {action.next_trigger_at
                  ? t('notifications_hub.next_run', {
                      when: formatInstant(action.next_trigger_at, locale),
                    })
                  : // Stated, never guessed: a routine whose next run the
                    // backend could not compute is a fact worth showing.
                    t('notifications_hub.next_run_unknown')}
              </p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
