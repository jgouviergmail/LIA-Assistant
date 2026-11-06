'use client';

/**
 * WeekView — the days of a view, an all-day row and the hours (ADR-369, mock-up
 * « Agenda » in « Semaine »): seven days, or one in the day view.
 *
 * Every hour of the day is drawn and the grid opens on the morning, on the
 * hour of « now » when today is shown, marked by a line that keeps time; timed
 * events sit in columns where they overlap and a cluster past the budget is
 * counted (« +N », a link to that day in the agenda) — `lib/workbench/calendar/
 * layout`. An event across midnight is drawn on each day it touches. A click on
 * an empty slot starts an event there: a pointer's shortcut to « New event »,
 * hidden from assistive technology and out of the tab order, since the button
 * is the keyboard's way and 168 slots would only be noise. From `lg` an event
 * living within one day is dragged to another time or day, and stretched by its
 * bottom edge (`CalendarDrag`); its editor stays the keyboard's way. On a phone
 * the grid keeps a readable width and scrolls sideways inside itself.
 */
import Link from 'next/link';
import { useEffect, useMemo, useRef, type CSSProperties, type MouseEvent } from 'react';

import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { callHref, type ShownEvent } from '@/lib/workbench/calendar/events';
import { longDay, timeLabel } from '@/lib/workbench/calendar/format';
import {
  MIN_SPAN_MINUTES,
  daySegments,
  layoutAllDay,
  layoutDay,
  type PositionedInput,
} from '@/lib/workbench/calendar/layout';

import { CalendarDragSurface, DraggableChip, DropColumn, type EventDrag } from './CalendarDrag';
import { EventChip, type EventChipProps } from './EventChip';
import { useWallClock } from './useWallClock';

/** One hour's height, in pixels. */
export const HOUR_PX = 48;
/** The hour the grid opens on. */
const MORNING = 7;
/** A chip this long has room for its call beside its title, at a target's size. */
const JOIN_MIN_MINUTES = 30;
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
  /** A click on an empty slot (a null time: the all-day row); left out where none can be written. */
  onSlot?: (day: string, time: string | null) => void;
  /** Dragging, where a screen and a calendar allow it. */
  drag?: EventDrag;
}

/** The grid's columns: the hours, then as many days as the view shows. */
function columnsOf(days: readonly string[]): CSSProperties {
  return { gridTemplateColumns: `3.5rem repeat(${days.length}, minmax(0, 1fr))` };
}

export function WeekView(props: WeekViewProps) {
  const { lng, days, today, zone } = props;
  const { t } = useTranslation(lng);
  const scroller = useRef<HTMLDivElement>(null);
  const clock = useWallClock(zone);
  const nowHour = days.includes(clock.date) ? Number(clock.time.slice(0, 2)) : null;
  const openingHour = useRef(nowHour === null ? MORNING : Math.max(0, nowHour - 1));
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = openingHour.current * HOUR_PX;
  }, []);
  const heading = new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'short',
    timeZone: 'UTC',
  });
  return (
    // Bounded on a phone too, so the grid scrolls inside itself and opens on the morning.
    <div ref={scroller} className="min-h-0 flex-1 overflow-auto max-lg:max-h-[70dvh]">
      <div className={cn(days.length > 1 && 'min-w-[44rem]')}>
        {/* The days and the all-day row stay in sight while the hours scroll under them. */}
        <div className="sticky top-0 z-10 bg-card">
          <div className="grid border-b" style={columnsOf(days)}>
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
        <TimedGrid {...props} now={clock.date} nowTime={clock.time} />
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
  onSlot,
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
  const dayColumns: CSSProperties = {
    gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`,
  };
  return (
    <div className="grid border-b" style={columnsOf(days)}>
      <span className="px-1 py-1.5 text-right text-[11px] text-muted-foreground">{label}</span>
      <div className="relative" style={{ gridColumn: '2 / -1' }}>
        {onSlot && (
          <div className="absolute inset-0 grid" style={dayColumns}>
            {days.map(day => (
              <button
                key={day}
                type="button"
                tabIndex={-1}
                aria-hidden="true"
                data-slot={day}
                className="hover:bg-primary/5 focus:outline-none"
                onClick={() => onSlot(day, null)}
              />
            ))}
          </div>
        )}
        <div
          className="pointer-events-none relative grid min-h-8 auto-rows-[1.5rem] gap-y-0.5 py-1 [&>*]:pointer-events-auto"
          style={dayColumns}
        >
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
                seriesLabel={event.recurring ? t('workbench.calendar.series') : undefined}
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
  onSlot,
  drag,
  now,
  nowTime,
}: WeekViewProps & { now: string; nowTime: string }) {
  const { t } = useTranslation(lng);
  const timed = useMemo(() => events.filter(event => !event.all_day), [events]);
  const grid = (
    <div className="grid" style={columnsOf(days)}>
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
          seriesLabel={t('workbench.calendar.series')}
          joinLabel={t('workbench.calendar.join_call')}
          nowTime={day === now ? nowTime : null}
          linkRef={linkRef}
          onSlot={onSlot}
          drag={drag}
        />
      ))}
    </div>
  );
  return drag ? (
    <CalendarDragSurface drag={drag} hourPx={HOUR_PX}>
      {grid}
    </CalendarDragSurface>
  ) : (
    grid
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
  seriesLabel: string;
  joinLabel: string;
  /** The wall time, on today's column. */
  nowTime: string | null;
  linkRef: (key: string, element: HTMLElement | null) => void;
  onSlot?: (day: string, time: string | null) => void;
  drag?: EventDrag;
}

function place(start: number, end: number, column: number, columns: number): CSSProperties {
  return {
    top: (start / 60) * HOUR_PX,
    height: (Math.max(end - start, MIN_SPAN_MINUTES) / 60) * HOUR_PX - 2,
    left: `${(column / columns) * 100}%`,
    width: `calc(${100 / columns}% - 2px)`,
  };
}

/** An hour's slot: its upper half the hour, its lower half half past. A keyboard's click is the hour. */
function slotTime(hour: number, click: MouseEvent<HTMLElement>): string {
  const box = click.currentTarget.getBoundingClientRect();
  const lower = click.detail > 0 && click.clientY - box.top >= box.height / 2;
  return `${String(hour).padStart(2, '0')}:${lower ? '30' : '00'}`;
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
  seriesLabel,
  joinLabel,
  nowTime,
  linkRef,
  onSlot,
  drag,
}: DayColumnProps) {
  const { segments, layout } = useMemo(() => {
    const found = new Map<
      string,
      { event: ShownEvent; input: PositionedInput; withinDay: boolean }
    >();
    for (const event of events) {
      const segment = daySegments(event.start, event.end, [day], zone)[day];
      if (segment)
        found.set(event.key, {
          event,
          input: { id: event.key, start: segment.start, end: segment.end },
          withinDay: !segment.continued && !segment.continues,
        });
    }
    return { segments: found, layout: layoutDay([...found.values()].map(entry => entry.input)) };
  }, [day, events, zone]);
  const body = (
    <>
      {HOURS.map(hour =>
        onSlot ? (
          <button
            key={hour}
            type="button"
            tabIndex={-1}
            aria-hidden="true"
            data-slot={`${day}T${String(hour).padStart(2, '0')}`}
            className="block w-full border-b border-border/60 hover:bg-primary/5 focus:outline-none"
            style={{ height: HOUR_PX }}
            onClick={click => onSlot(day, slotTime(hour, click))}
          />
        ) : (
          <div
            key={hour}
            aria-hidden="true"
            className="border-b border-border/60"
            style={{ height: HOUR_PX }}
          />
        )
      )}
      {layout.placed.map(placed => {
        const entry = segments.get(placed.id);
        if (!entry) return null;
        const { event, withinDay } = entry;
        const call = callHref(event.conference_url);
        const chip: EventChipProps = {
          href: hrefOf(event),
          summary: event.summary,
          untitled,
          color: event.color,
          current: event.key === openId,
          linkRef: element => linkRef(event.key, element),
          times: `${timeLabel(event.start, zone, lng)} – ${timeLabel(event.end, zone, lng)}`,
          seriesLabel: event.recurring ? seriesLabel : undefined,
          join:
            call && placed.end - placed.start >= JOIN_MIN_MINUTES
              ? { href: call, label: `${joinLabel} — ${event.summary || untitled}` }
              : undefined,
          className: 'absolute',
          style: place(placed.start, placed.end, placed.column, placed.columns),
        };
        return drag && withinDay && drag.allows(event) ? (
          <DraggableChip key={placed.id} event={event} day={day} chip={chip} />
        ) : (
          <EventChip key={placed.id} {...chip} />
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
      {nowTime !== null && <NowLine time={nowTime} />}
    </>
  );
  const height = 24 * HOUR_PX;
  return drag ? (
    <DropColumn day={day} height={height}>
      {body}
    </DropColumn>
  ) : (
    <div className="relative border-l" style={{ height }}>
      {body}
    </div>
  );
}

/** Where the clock stands: drawn over the events, deaf to the pointer. */
function NowLine({ time }: { time: string }) {
  const [hour, minute] = time.split(':').map(Number);
  return (
    <div
      aria-hidden="true"
      data-now-line=""
      className="pointer-events-none absolute inset-x-0 z-[2] h-0.5 bg-primary before:absolute before:-left-1 before:-top-1 before:h-2.5 before:w-2.5 before:rounded-full before:bg-primary"
      style={{ top: ((hour * 60 + minute) / 60) * HOUR_PX }}
    />
  );
}
