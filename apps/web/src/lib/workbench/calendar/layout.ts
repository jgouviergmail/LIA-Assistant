/**
 * Where the calendar views draw each event (ADR-369): pure geometry.
 *
 * A day of the week grid places its timed events in COLUMNS: events that
 * overlap — transitively, a cluster — share the cluster's width, a column freed
 * earlier is reused, and a very short event counts as `MIN_SPAN_MINUTES` long
 * so its label is never drawn under its neighbour. Past the column budget the
 * last column is given to a count (« +N ») of what it could not draw — never an
 * event drawn on top of another. A timed event is cut into one segment per day
 * it touches, on the account's wall; an all-day event is a bar across its days
 * (the end exclusive), in lanes, with the same budget rule per day.
 */
import {
  addDays,
  daysBetween,
  daysFrom,
  instantToWall,
  wallTimeToInstant,
  weekStart,
} from './zoned';

/** The shortest an event is drawn, in minutes (its label must fit). */
export const MIN_SPAN_MINUTES = 20;
/** Columns of one day, or lanes of the all-day row, before « +N ». */
export const DEFAULT_BUDGET = 3;
const DAY_MINUTES = 24 * 60;

/** A timed event of one day, in minutes from that day's midnight. */
export interface PositionedInput {
  id: string;
  start: number;
  end: number;
}

/** It, with the column it is drawn in and the columns its cluster shares. */
export interface PositionedEvent extends PositionedInput {
  column: number;
  columns: number;
}

/** What a cluster could not draw: counted in its last column. */
export interface MoreSlot {
  start: number;
  end: number;
  column: number;
  columns: number;
  ids: string[];
}

export interface DayLayout {
  placed: PositionedEvent[];
  more: MoreSlot[];
}

interface Columned extends PositionedInput {
  column: number;
}

function placeCluster(
  cluster: Columned[],
  columns: number,
  budget: number,
  layout: DayLayout
): void {
  const shown = Math.min(columns, budget);
  const hidden = cluster.filter(event => columns > budget && event.column >= budget - 1);
  for (const event of cluster) {
    if (!hidden.includes(event)) layout.placed.push({ ...event, columns: shown });
  }
  if (hidden.length > 0) {
    layout.more.push({
      start: Math.min(...hidden.map(event => event.start)),
      end: Math.max(...hidden.map(event => event.end)),
      column: budget - 1,
      columns: shown,
      ids: hidden.map(event => event.id),
    });
  }
}

/**
 * @param events - The day's timed events.
 * @param budget - Columns drawn before the rest is counted.
 * @returns Each drawn event's column, and the counts past the budget.
 */
export function layoutDay(events: readonly PositionedInput[], budget = DEFAULT_BUDGET): DayLayout {
  const ordered = [...events].sort((a, b) => a.start - b.start || b.end - a.end);
  const layout: DayLayout = { placed: [], more: [] };
  let cluster: Columned[] = [];
  let columnEnds: number[] = [];
  let clusterEnd = -1;
  const shownEnd = (event: PositionedInput) => Math.max(event.end, event.start + MIN_SPAN_MINUTES);
  for (const event of ordered) {
    if (event.start >= clusterEnd && cluster.length > 0) {
      placeCluster(cluster, columnEnds.length, budget, layout);
      cluster = [];
      columnEnds = [];
    }
    let column = columnEnds.findIndex(end => end <= event.start);
    if (column === -1) column = columnEnds.length;
    columnEnds[column] = shownEnd(event);
    cluster.push({ ...event, column });
    clusterEnd = Math.max(cluster.length === 1 ? 0 : clusterEnd, shownEnd(event));
  }
  if (cluster.length > 0) placeCluster(cluster, columnEnds.length, budget, layout);
  return layout;
}

/** One day's part of a timed event, on the account's wall. */
export interface DaySegment {
  start: number;
  end: number;
  /** It goes on past this day's midnight. */
  continues: boolean;
  /** It began before this day. */
  continued: boolean;
}

function wallMinutes(instant: Date, zone: string): number {
  const [hour, minute] = instantToWall(instant, zone).time.split(':').map(Number);
  return hour * 60 + minute;
}

/**
 * @param start - The event's start, an instant (RFC 3339).
 * @param end - Its end, an instant.
 * @param days - The days of the view.
 * @param zone - The account's zone.
 * @returns Its segment on each day it touches.
 */
export function daySegments(
  start: string,
  end: string,
  days: readonly string[],
  zone: string
): Record<string, DaySegment> {
  const from = new Date(start).getTime();
  const to = new Date(end).getTime();
  const segments: Record<string, DaySegment> = {};
  for (const day of days) {
    const dayStart = wallTimeToInstant(day, '00:00', zone).getTime();
    const next = wallTimeToInstant(addDays(day, 1), '00:00', zone).getTime();
    const shownFrom = Math.max(from, dayStart);
    const shownTo = Math.min(to, next);
    if (shownTo <= shownFrom) continue;
    segments[day] = {
      start: shownFrom === dayStart ? 0 : wallMinutes(new Date(shownFrom), zone),
      end: shownTo === next ? DAY_MINUTES : wallMinutes(new Date(shownTo), zone),
      continues: to > next,
      continued: from < dayStart,
    };
  }
  return segments;
}

/** An all-day event: its first day and the day after its last (exclusive). */
export interface DayBarInput {
  id: string;
  start: string;
  end: string;
}

/** Its bar: the first and last index of the view's days it covers, and its lane. */
export interface DayBar {
  id: string;
  first: number;
  last: number;
  lane: number;
}

export interface AllDayLayout {
  placed: DayBar[];
  /** Per day index, the bars that day could not draw. */
  more: Record<number, string[]>;
}

/**
 * @param bars - The all-day events.
 * @param days - The days of the view, in order.
 * @param budget - Lanes drawn before a day's rest is counted.
 * @returns Each drawn bar's span and lane, and each day's count past the budget.
 */
export function layoutAllDay(
  bars: readonly DayBarInput[],
  days: readonly string[],
  budget = DEFAULT_BUDGET
): AllDayLayout {
  const spans = bars
    .map(bar => ({
      id: bar.id,
      first: Math.max(0, daysBetween(days[0], bar.start)),
      last: Math.min(days.length - 1, daysBetween(days[0], bar.end) - 1),
    }))
    .filter(span => span.last >= span.first)
    .sort((a, b) => a.first - b.first || b.last - b.first - (a.last - a.first));
  const laneEnds: number[] = [];
  const crowd = days.map(() => 0);
  const laned = spans.map(span => {
    let lane = laneEnds.findIndex(end => end < span.first);
    if (lane === -1) lane = laneEnds.length;
    laneEnds[lane] = span.last;
    for (let day = span.first; day <= span.last; day += 1) crowd[day] += 1;
    return { ...span, lane };
  });
  const layout: AllDayLayout = { placed: [], more: {} };
  for (const bar of laned) {
    const crowded = crowd.slice(bar.first, bar.last + 1).some(count => count > budget);
    if (bar.lane < budget - 1 || (bar.lane === budget - 1 && !crowded)) {
      layout.placed.push(bar);
      continue;
    }
    for (let day = bar.first; day <= bar.last; day += 1) {
      layout.more[day] = [...(layout.more[day] ?? []), bar.id];
    }
  }
  return layout;
}

/** The days a month grid shows: six weeks, always. */
export const MONTH_GRID_DAYS = 42;

/**
 * @param day - Any day of the month.
 * @param firstDay - The locale's first weekday (1-7).
 * @returns Six weeks from the start of the week holding the month's first day.
 */
export function monthGrid(day: string, firstDay: number): string[] {
  return daysFrom(weekStart(`${day.slice(0, 7)}-01`, firstDay), MONTH_GRID_DAYS);
}

/**
 * @param event - An event of a view.
 * @param zone - The account's zone.
 * @returns The days it touches on the account's wall: its first, and the day
 *   after its last (exclusive) — a timed event ending at midnight ends there.
 */
export function eventDays(
  event: { all_day: boolean; start: string; end: string },
  zone: string
): { start: string; end: string } {
  if (event.all_day) return { start: event.start, end: event.end };
  const first = instantToWall(new Date(event.start), zone).date;
  // The last minute it holds is the minute before its end.
  const last = instantToWall(new Date(new Date(event.end).getTime() - 60_000), zone).date;
  return { start: first, end: addDays(last < first ? first : last, 1) };
}
