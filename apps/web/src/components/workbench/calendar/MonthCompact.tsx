'use client';

/**
 * MonthCompact — the month on a phone (ADR-369, lot 2).
 *
 * Bars need a width a phone does not have, so the month is the days in reach of
 * a thumb, each with a dot per calendar it holds something in, and the picked
 * day's events below as the agenda lists them. Picking a day moves the address.
 * The days are walked with the keyboard (the grid pattern).
 */
import { useMemo } from 'react';

import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { ShownEvent } from '@/lib/workbench/calendar/events';
import { longDay } from '@/lib/workbench/calendar/format';
import { eventDays } from '@/lib/workbench/calendar/layout';
import { daysBetween, daysFrom } from '@/lib/workbench/calendar/zoned';

import { AgendaEntries, entriesOf } from './AgendaView';
import { CalendarSwatch } from './EventChip';
import { useRovingGrid } from './useRovingGrid';

const WEEK = 7;
/** The dots a day draws: its count is in its name. */
const DOTS_MAX = 3;

export interface MonthCompactProps {
  lng: Language;
  /** The 42 days of the grid. */
  days: readonly string[];
  /** The month shown, `YYYY-MM` (its other days are muted). */
  month: string;
  /** The day picked. */
  day: string;
  today: string;
  zone: string;
  events: readonly ShownEvent[];
  openId: string | null;
  hrefOf: (event: ShownEvent) => string;
  linkRef: (key: string, element: HTMLElement | null) => void;
  onPick: (day: string) => void;
}

/** @returns Each day's events, for its dots and its count. */
function eventsByDay(
  events: readonly ShownEvent[],
  days: readonly string[],
  zone: string
): Map<string, ShownEvent[]> {
  const shown = new Set(days);
  const held = new Map<string, ShownEvent[]>();
  for (const event of events) {
    const { start, end } = eventDays(event, zone);
    for (const day of daysFrom(start, Math.max(1, daysBetween(start, end)))) {
      if (!shown.has(day)) continue;
      const list = held.get(day);
      if (list) list.push(event);
      else held.set(day, [event]);
    }
  }
  return held;
}

export function MonthCompact({
  lng,
  days,
  month,
  day,
  today,
  zone,
  events,
  openId,
  hrefOf,
  linkRef,
  onPick,
}: MonthCompactProps) {
  const { t } = useTranslation(lng);
  const grid = useRovingGrid(days.length, Math.max(0, days.indexOf(day)));
  const held = useMemo(() => eventsByDay(events, days, zone), [days, events, zone]);
  const entries = useMemo(() => entriesOf(day, events, zone, lng), [day, events, lng, zone]);
  const heading = new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'narrow',
    timeZone: 'UTC',
  });
  const weeks = Array.from({ length: days.length / WEEK }, (_, week) =>
    days.slice(week * WEEK, week * WEEK + WEEK)
  );
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div role="grid" aria-label={t('workbench.calendar.views.month')} className="border-b px-1">
        <div role="row" className="grid grid-cols-7">
          {weeks[0].map(item => (
            <span
              key={item}
              role="columnheader"
              className="py-1.5 text-center text-xs text-muted-foreground"
            >
              {heading.format(new Date(`${item}T00:00:00Z`))}
            </span>
          ))}
        </div>
        {weeks.map((week, row) => (
          <div key={week[0]} role="row" className="grid grid-cols-7">
            {week.map((item, column) => {
              const dayEvents = held.get(item) ?? [];
              return (
                <div key={item} role="gridcell">
                  <button
                    {...grid.cell(row * WEEK + column)}
                    type="button"
                    aria-pressed={item === day}
                    aria-label={`${longDay(item, lng)}, ${t('workbench.calendar.day_events', {
                      count: dayEvents.length,
                    })}`}
                    onClick={() => onPick(item)}
                    className={cn(
                      'flex h-12 w-full flex-col items-center justify-start gap-0.5 rounded-md pt-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-pressed:bg-primary/10',
                      item.slice(0, 7) !== month && 'text-muted-foreground'
                    )}
                  >
                    <span
                      className={cn(
                        'flex h-6 w-6 items-center justify-center rounded-full font-semibold',
                        item === today && 'bg-primary text-primary-foreground'
                      )}
                    >
                      {Number(item.slice(8))}
                    </span>
                    <span className="flex h-1.5 gap-0.5" aria-hidden="true">
                      {dayEvents.slice(0, DOTS_MAX).map(event => (
                        <CalendarSwatch
                          key={event.key}
                          color={event.color}
                          className="h-1.5 w-1.5 rounded-full"
                        />
                      ))}
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <section aria-label={longDay(day, lng)} className="px-3 py-3">
        <h3 className="mb-2 text-sm font-semibold">{longDay(day, lng)}</h3>
        {entries.length > 0 ? (
          <AgendaEntries
            lng={lng}
            entries={entries}
            openId={openId}
            hrefOf={hrefOf}
            linkRef={linkRef}
          />
        ) : (
          <p className="text-sm text-muted-foreground">{t('workbench.calendar.empty_day')}</p>
        )}
      </section>
    </div>
  );
}
