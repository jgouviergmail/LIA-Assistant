'use client';

/**
 * WeekView — seven days, an all-day row and the hours (ADR-369, mock-up
 * « Agenda » in « Semaine »).
 *
 * Every hour of the day is drawn and the grid opens on the morning; timed
 * events sit in columns where they overlap and a cluster past the budget is
 * counted (« +N », a link to that day in the agenda) — `lib/workbench/calendar/
 * layout`. An event across midnight is drawn on each day it touches. On a
 * phone the grid keeps a readable width and scrolls sideways inside itself.
 */
import Link from 'next/link';
import { useEffect, useMemo, useRef, type CSSProperties } from 'react';

import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { ShownEvent } from '@/lib/workbench/calendar/events';
import { longDay, timeLabel } from '@/lib/workbench/calendar/format';
import {
  MIN_SPAN_MINUTES,
  daySegments,
  layoutAllDay,
  layoutDay,
  type PositionedInput,
} from '@/lib/workbench/calendar/layout';

import { EventChip } from './EventChip';

/** One hour's height, in pixels. */
const HOUR_PX = 48;
/** The hour the grid opens on. */
const MORNING = 7;
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

export interface WeekViewProps {
  lng: Language;
  days: readonly string[];
  today: string;
  zone: string;
  events: readonly ShownEvent[];
  openId: string | null;
  hrefOf: (event: ShownEvent) => string;
  agendaHref: (day: string) => string;
  /** Hands each event's link to the drill-down focus. */
  linkRef: (key: string, element: HTMLElement | null) => void;
}

export function WeekView(props: WeekViewProps) {
  const { lng, days, today } = props;
  const { t } = useTranslation(lng);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = MORNING * HOUR_PX;
  }, []);
  const heading = new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'short',
    timeZone: 'UTC',
  });
  return (
    // Bounded on a phone too, so the grid scrolls inside itself and opens on the morning.
    <div ref={scroller} className="min-h-0 flex-1 overflow-auto max-lg:max-h-[70dvh]">
      <div className="min-w-[44rem]">
        {/* The days and the all-day row stay in sight while the hours scroll under them. */}
        <div className="sticky top-0 z-10 bg-card">
          <div className="grid grid-cols-[3.5rem_repeat(7,minmax(0,1fr))] border-b">
            <span aria-hidden="true" />
            {days.map(day => (
              <div key={day} className="py-2 text-center">
                <span className="block text-xs text-muted-foreground">
                  {heading.format(new Date(`${day}T00:00:00Z`))}
                </span>
                <span
                  className={cn(
                    'mx-auto flex h-7 w-7 items-center justify-center rounded-full text-sm font-bold',
                    day === today && 'bg-primary text-primary-foreground'
                  )}
                >
                  {Number(day.slice(8))}
                </span>
              </div>
            ))}
          </div>
          <AllDayRow {...props} label={t('workbench.calendar.all_day_row')} />
        </div>
        <TimedGrid {...props} />
      </div>
    </div>
  );
}

function AllDayRow({
  lng,
  days,
  events,
  openId,
  hrefOf,
  agendaHref,
  linkRef,
  label,
}: WeekViewProps & { label: string }) {
  const { t } = useTranslation(lng);
  const allDay = useMemo(() => events.filter(event => event.all_day), [events]);
  const layout = useMemo(
    () =>
      layoutAllDay(
        allDay.map(event => ({ id: event.key, start: event.start, end: event.end })),
        days
      ),
    [allDay, days]
  );
  const byKey = new Map(allDay.map(event => [event.key, event]));
  return (
    <div className="grid grid-cols-[3.5rem_repeat(7,minmax(0,1fr))] border-b">
      <span className="px-1 py-1.5 text-right text-[11px] text-muted-foreground">{label}</span>
      <div className="col-span-7 grid auto-rows-[1.5rem] grid-cols-7 gap-y-0.5 py-1">
        {layout.placed.map(bar => {
          const event = byKey.get(bar.id);
          if (!event) return null;
          return (
            <EventChip
              key={bar.id}
              href={hrefOf(event)}
              summary={event.summary}
              untitled={t('workbench.calendar.no_title')}
              color={event.color}
              current={event.key === openId}
              linkRef={element => linkRef(event.key, element)}
              className="mx-0.5"
              style={{ gridColumn: `${bar.first + 1} / ${bar.last + 2}`, gridRow: bar.lane + 1 }}
            />
          );
        })}
        {Object.entries(layout.more).map(([day, keys]) => (
          <Link
            key={day}
            href={agendaHref(days[Number(day)])}
            scroll={false}
            className="mx-0.5 truncate rounded-md px-1.5 text-xs font-semibold text-primary hover:underline"
            style={{ gridColumn: Number(day) + 1, gridRow: 3 }}
            aria-label={t('workbench.calendar.more_label', {
              count: keys.length,
              day: longDay(days[Number(day)], lng),
            })}
          >
            {t('workbench.calendar.more', { count: keys.length })}
          </Link>
        ))}
      </div>
    </div>
  );
}

function TimedGrid({
  lng,
  days,
  zone,
  events,
  openId,
  hrefOf,
  agendaHref,
  linkRef,
}: WeekViewProps) {
  const { t } = useTranslation(lng);
  const timed = useMemo(() => events.filter(event => !event.all_day), [events]);
  return (
    <div className="grid grid-cols-[3.5rem_repeat(7,minmax(0,1fr))]">
      <div aria-hidden="true">
        {HOURS.map(hour => (
          <div key={hour} className="relative text-right" style={{ height: HOUR_PX }}>
            {hour > 0 && (
              <span className="absolute -top-2 right-1 text-[11px] text-muted-foreground">
                {timeLabel(`2026-01-01T${String(hour).padStart(2, '0')}:00:00Z`, 'UTC', lng)}
              </span>
            )}
          </div>
        ))}
      </div>
      {days.map(day => (
        <DayColumn
          key={day}
          lng={lng}
          day={day}
          zone={zone}
          events={timed}
          openId={openId}
          hrefOf={hrefOf}
          moreHref={agendaHref(day)}
          moreLabel={count => t('workbench.calendar.more', { count })}
          moreName={count => t('workbench.calendar.more_label', { count, day: longDay(day, lng) })}
          untitled={t('workbench.calendar.no_title')}
          linkRef={linkRef}
        />
      ))}
    </div>
  );
}

interface DayColumnProps {
  lng: Language;
  day: string;
  zone: string;
  events: readonly ShownEvent[];
  openId: string | null;
  hrefOf: (event: ShownEvent) => string;
  moreHref: string;
  moreLabel: (count: number) => string;
  /** The « +N » link's accessible name: how many, on which day. */
  moreName: (count: number) => string;
  untitled: string;
  linkRef: (key: string, element: HTMLElement | null) => void;
}

function place(start: number, end: number, column: number, columns: number): CSSProperties {
  return {
    top: (start / 60) * HOUR_PX,
    height: (Math.max(end - start, MIN_SPAN_MINUTES) / 60) * HOUR_PX - 2,
    left: `${(column / columns) * 100}%`,
    width: `calc(${100 / columns}% - 2px)`,
  };
}

function DayColumn({
  lng,
  day,
  zone,
  events,
  openId,
  hrefOf,
  moreHref,
  moreLabel,
  moreName,
  untitled,
  linkRef,
}: DayColumnProps) {
  const { segments, layout } = useMemo(() => {
    const found = new Map<string, { event: ShownEvent; input: PositionedInput }>();
    for (const event of events) {
      const segment = daySegments(event.start, event.end, [day], zone)[day];
      if (segment)
        found.set(event.key, {
          event,
          input: { id: event.key, start: segment.start, end: segment.end },
        });
    }
    return { segments: found, layout: layoutDay([...found.values()].map(entry => entry.input)) };
  }, [day, events, zone]);
  return (
    <div className="relative border-l" style={{ height: 24 * HOUR_PX }}>
      {HOURS.map(hour => (
        <div
          key={hour}
          aria-hidden="true"
          className="border-b border-border/60"
          style={{ height: HOUR_PX }}
        />
      ))}
      {layout.placed.map(placed => {
        const entry = segments.get(placed.id);
        if (!entry) return null;
        const { event } = entry;
        return (
          <EventChip
            key={placed.id}
            href={hrefOf(event)}
            summary={event.summary}
            untitled={untitled}
            color={event.color}
            current={event.key === openId}
            linkRef={element => linkRef(event.key, element)}
            times={`${timeLabel(event.start, zone, lng)} – ${timeLabel(event.end, zone, lng)}`}
            className="absolute"
            style={place(placed.start, placed.end, placed.column, placed.columns)}
          />
        );
      })}
      {layout.more.map(slot => (
        <Link
          key={slot.ids.join('|')}
          href={moreHref}
          scroll={false}
          className="absolute flex items-start justify-center rounded-md bg-muted px-1 py-0.5 text-xs font-semibold text-primary hover:underline"
          style={place(slot.start, slot.end, slot.column, slot.columns)}
          aria-label={moreName(slot.ids.length)}
        >
          {moreLabel(slot.ids.length)}
        </Link>
      ))}
    </div>
  );
}
