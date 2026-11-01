'use client';

/**
 * MonthView — six weeks, always (ADR-369, Task 5b.1).
 *
 * The grid starts on the locale's first weekday; each week draws its events as
 * bars across the days they touch on the account's wall — a timed one with its
 * hour — in lanes, and a day past the lane budget says how many more it holds
 * (« +N », a link to that day in the agenda). Each day's number is a link to
 * that day in the agenda, and the days are walked with the keyboard (the grid
 * pattern: arrows, Home, End).
 */
import Link from 'next/link';
import { useMemo } from 'react';

import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { ShownEvent } from '@/lib/workbench/calendar/events';
import { longDay, timeLabel } from '@/lib/workbench/calendar/format';
import { eventDays, layoutAllDay } from '@/lib/workbench/calendar/layout';

import { EventChip } from './EventChip';
import { useRovingGrid } from './useRovingGrid';

const WEEK = 7;
/** Lanes a week draws before a day's rest is counted. */
const MONTH_LANES = 3;
/** Where the first lane sits under the day's number, and one lane's height (px). */
const LANE_TOP = 32;
const LANE_PX = 22;

export interface MonthViewProps {
  lng: Language;
  /** The 42 days of the grid. */
  days: readonly string[];
  /** The month shown, `YYYY-MM` (its other days are muted). */
  month: string;
  today: string;
  zone: string;
  events: readonly ShownEvent[];
  openId: string | null;
  hrefOf: (event: ShownEvent) => string;
  agendaHref: (day: string) => string;
  linkRef: (key: string, element: HTMLElement | null) => void;
}

export function MonthView(props: MonthViewProps) {
  const { lng, days, today } = props;
  const { t } = useTranslation(lng);
  const start = Math.max(0, days.indexOf(today));
  const grid = useRovingGrid(days.length, start);
  const heading = new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'short',
    timeZone: 'UTC',
  });
  const weeks = Array.from({ length: days.length / WEEK }, (_, week) =>
    days.slice(week * WEEK, week * WEEK + WEEK)
  );
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div role="grid" aria-label={t('workbench.calendar.views.month')} className="min-w-[36rem]">
        <div role="row" className="grid grid-cols-7 border-b bg-card">
          {weeks[0].map(day => (
            <span
              key={day}
              role="columnheader"
              className="py-1.5 text-center text-xs text-muted-foreground"
            >
              {heading.format(new Date(`${day}T00:00:00Z`))}
            </span>
          ))}
        </div>
        {weeks.map((week, index) => (
          <WeekRow key={week[0]} {...props} week={week} offset={index * WEEK} grid={grid} />
        ))}
      </div>
    </div>
  );
}

interface WeekRowProps extends MonthViewProps {
  week: readonly string[];
  offset: number;
  grid: ReturnType<typeof useRovingGrid>;
}

function WeekRow({
  lng,
  week,
  offset,
  grid,
  month,
  today,
  zone,
  events,
  openId,
  hrefOf,
  agendaHref,
  linkRef,
}: WeekRowProps) {
  const { t } = useTranslation(lng);
  const byKey = useMemo(() => new Map(events.map(event => [event.key, event])), [events]);
  const layout = useMemo(
    () =>
      layoutAllDay(
        events.map(event => ({ id: event.key, ...eventDays(event, zone) })),
        week,
        MONTH_LANES
      ),
    [events, week, zone]
  );
  const startsIn = (index: number) => layout.placed.filter(bar => bar.first === index);
  return (
    <div role="row" className="grid min-h-28 grid-cols-7 border-b">
      {week.map((day, index) => (
        // Every link lives in a cell: a bar is drawn from the cell it starts in, across its days.
        <div key={day} role="gridcell" className="relative border-l px-1 pt-1 first:border-l-0">
          <Link
            {...grid.cell(offset + index)}
            href={agendaHref(day)}
            scroll={false}
            aria-label={longDay(day, lng)}
            className={cn(
              'inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              day === today && 'bg-primary text-primary-foreground',
              day.slice(0, 7) !== month && day !== today && 'text-muted-foreground'
            )}
          >
            {Number(day.slice(8))}
          </Link>
          {startsIn(index).map(bar => {
            const event = byKey.get(bar.id);
            if (!event) return null;
            const span = bar.last - bar.first + 1;
            const label = event.all_day
              ? event.summary
              : `${timeLabel(event.start, zone, lng)} ${event.summary}`;
            return (
              <EventChip
                key={bar.id}
                href={hrefOf(event)}
                summary={label}
                untitled={t('workbench.calendar.no_title')}
                color={event.color}
                current={event.key === openId}
                linkRef={element => linkRef(event.key, element)}
                className="absolute z-[1] py-0"
                style={{
                  top: LANE_TOP + bar.lane * LANE_PX,
                  left: 2,
                  width: `calc(${span * 100}% - 4px)`,
                }}
              />
            );
          })}
          {layout.more[index] && (
            <Link
              href={agendaHref(day)}
              scroll={false}
              aria-label={t('workbench.calendar.more_label', {
                count: layout.more[index].length,
                day: longDay(day, lng),
              })}
              className="absolute left-1 text-xs font-semibold text-primary hover:underline"
              style={{ top: LANE_TOP + (MONTH_LANES - 1) * LANE_PX }}
            >
              {t('workbench.calendar.more', { count: layout.more[index].length })}
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}
