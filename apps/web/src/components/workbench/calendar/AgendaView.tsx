'use client';

/**
 * AgendaView — the view's days as a list (ADR-369, mock-up « Agenda »).
 *
 * Each day with something in it, its all-day events first, then its timed ones
 * by their start on the account's wall; an event across midnight shows on each
 * day it touches and says it goes on. The day a « +N » of the week points at
 * opens scrolled to.
 */
import Link from 'next/link';
import { useEffect, useMemo, useRef } from 'react';

import { EmptyState } from '@/components/ui/empty-state';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { ShownEvent } from '@/lib/workbench/calendar/events';
import { longDay, timeLabel } from '@/lib/workbench/calendar/format';
import { daySegments } from '@/lib/workbench/calendar/layout';

import { CalendarSwatch } from './EventChip';

export interface AgendaViewProps {
  lng: Language;
  days: readonly string[];
  today: string;
  zone: string;
  events: readonly ShownEvent[];
  openId: string | null;
  /** The day to open on (a « +N » of the week). */
  focusDay: string | null;
  hrefOf: (event: ShownEvent) => string;
  /** Hands each event's link to the drill-down focus. */
  linkRef: (key: string, element: HTMLElement | null) => void;
}

interface AgendaEntry {
  event: ShownEvent;
  /** Its times on this day, or null for an all-day event. */
  times: string | null;
}

function entriesOf(
  day: string,
  events: readonly ShownEvent[],
  zone: string,
  lng: Language
): AgendaEntry[] {
  const allDay = events
    .filter(event => event.all_day && event.start <= day && day < event.end)
    .map(event => ({ event, times: null }));
  const timed: AgendaEntry[] = [];
  for (const event of events) {
    if (event.all_day) continue;
    const segment = daySegments(event.start, event.end, [day], zone)[day];
    if (!segment) continue;
    const from = segment.continued ? '…' : timeLabel(event.start, zone, lng);
    const to = segment.continues ? '…' : timeLabel(event.end, zone, lng);
    timed.push({ event, times: `${from} – ${to}` });
  }
  return [...allDay, ...timed];
}

export function AgendaView({
  lng,
  days,
  today,
  zone,
  events,
  openId,
  focusDay,
  hrefOf,
  linkRef,
}: AgendaViewProps) {
  const { t } = useTranslation(lng);
  const list = useRef<HTMLDivElement>(null);
  const focused = useRef<HTMLElement>(null);
  const listed = useMemo(
    () => days.map(day => ({ day, entries: entriesOf(day, events, zone, lng) })),
    [days, events, zone, lng]
  );
  // The list scrolls itself to the day; the page never moves (a phone keeps the toolbar).
  useEffect(() => {
    if (list.current && focused.current) {
      list.current.scrollTop = focused.current.offsetTop - list.current.offsetTop;
    }
  }, [focusDay]);
  const shown = listed.filter(item => item.entries.length > 0);
  if (shown.length === 0) {
    return <EmptyState className="flex-1" description={t('workbench.calendar.empty')} />;
  }
  return (
    <div ref={list} className="min-h-0 flex-1 overflow-y-auto">
      {shown.map(({ day, entries }) => (
        <section
          key={day}
          ref={day === focusDay ? focused : undefined}
          aria-labelledby={`agenda-${day}`}
          className="border-b px-4 py-3"
        >
          <h3
            id={`agenda-${day}`}
            className={cn(
              'mb-2 text-sm font-semibold',
              day === today ? 'text-primary' : 'text-foreground'
            )}
          >
            {longDay(day, lng)}
          </h3>
          <ul className="space-y-1.5">
            {entries.map(({ event, times }) => (
              <li key={event.key}>
                <Link
                  ref={element => linkRef(event.key, element)}
                  href={hrefOf(event)}
                  scroll={false}
                  aria-current={event.key === openId ? 'true' : undefined}
                  className="flex items-start gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:bg-primary/10"
                >
                  <span className="w-28 shrink-0 text-xs text-muted-foreground">
                    {times ?? t('workbench.calendar.all_day')}
                  </span>
                  <CalendarSwatch color={event.color} className="mt-1 h-2.5 w-2.5" />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {event.summary || t('workbench.calendar.no_title')}
                    </span>
                    {event.location && (
                      <span className="block truncate text-xs text-muted-foreground">
                        {event.location}
                      </span>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
