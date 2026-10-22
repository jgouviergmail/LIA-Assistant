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
 * Neither does a condition routine (ADR-322): its trigger is the system's next
 * CHECK, and its sentence already says how often that happens.
 *
 * Both states are SAID: an enabled routine wears a green « Enabled » badge
 * (owner request 2026-10-21) where it used to wear nothing, so only the
 * exception was legible; a disabled one keeps the grey the owner rule reserves
 * for inactive elements. One tone table decides both (`lifecycleTone`).
 */

import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { formatInstant } from '@/lib/format-instant';
import { lifecycleTone } from '@/lib/status-tone';

export interface ScheduledActionRow {
  id: string;
  title: string;
  is_enabled: boolean;
  trigger_kind: 'time' | 'condition';
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
    <ul className="divide-y divide-border" role="list">
      {actions.map(action => (
        <li key={action.id} className="min-w-0 py-4 first:pt-0 last:pb-0">
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-baseline gap-2">
              {/* The title in bold, the schedule plain beneath it (owner
                  request 2026-10-21): the name is what a reader scans for. */}
              <span className="min-w-0 break-words text-sm font-semibold leading-relaxed text-foreground">
                {action.title}
              </span>
              <Badge
                variant={lifecycleTone(action.is_enabled ? 'active' : 'disabled')}
                size="sm"
                className="uppercase tracking-wide"
              >
                {action.is_enabled
                  ? t('notifications_hub.routine_enabled')
                  : t('notifications_hub.routine_disabled')}
              </Badge>
            </p>
            <p className="mt-1 break-words text-xs leading-relaxed text-muted-foreground">
              {action.schedule_display}
            </p>
            {action.is_enabled && action.trigger_kind !== 'condition' && (
              <p className="mt-1 text-xs tabular-nums leading-relaxed text-muted-foreground">
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
