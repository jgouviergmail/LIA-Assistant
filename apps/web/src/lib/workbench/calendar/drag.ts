/**
 * Where a dragged event lands (ADR-369, lot 2): pure.
 *
 * dnd-kit reports pixels and the day under the pointer; the API takes wall
 * times. A drag is read in quarters of an hour. A move keeps the event's length
 * and never leaves the day it was dropped on; a resize keeps the start and
 * leaves the event one step long at least, midnight at the latest. Only an event
 * that lives within one day is dragged, so its bounds are minutes of that day.
 * Nothing here knows the zone but `wallFieldsOf`: what a person drags is a
 * clock on the wall, and a clock change moves no event twice.
 */
import { addDays, instantToWall } from './zoned';

/** The step a drag moves by, in minutes. */
export const SNAP_MINUTES = 15;

const DAY_MINUTES = 24 * 60;
const MIDNIGHT = '00:00';

/** The wall bounds of a timed event. */
export interface WallBounds {
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
}

/** A drop: which edge moved, by how much, and the day under the pointer. */
export interface EventDrop {
  edge: 'move' | 'end';
  minutes: number;
  day: string;
}

/**
 * @param pixels - How far the pointer went, on the hours' axis.
 * @param hourPx - One hour's height.
 * @returns That distance in minutes, to the nearest step.
 */
export function snappedMinutes(pixels: number, hourPx: number): number {
  const steps = Math.round(((pixels / hourPx) * 60) / SNAP_MINUTES);
  // `|| 0`: a small drag upward rounds to -0, which is no distance.
  return steps * SNAP_MINUTES || 0;
}

function minutesOf(time: string): number {
  const [hour, minute] = time.split(':').map(Number);
  return hour * 60 + minute;
}

function clockOf(minutes: number): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

/** The bounds of `day` from minutes of that day, midnight being the next day's start. */
function boundsOn(day: string, start: number, end: number): WallBounds {
  const endsAtMidnight = end >= DAY_MINUTES;
  return {
    startDate: day,
    startTime: clockOf(start),
    endDate: endsAtMidnight ? addDays(day, 1) : day,
    endTime: endsAtMidnight ? MIDNIGHT : clockOf(end),
  };
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/**
 * @param fields - The event's wall bounds (with whatever else the form holds).
 * @param drop - The drop.
 * @returns The fields after the drop; null when it changes nothing.
 */
export function droppedFields<T extends WallBounds>(fields: T, drop: EventDrop): T | null {
  const start = minutesOf(fields.startTime);
  const sameDay = fields.endDate === fields.startDate;
  const end = sameDay ? minutesOf(fields.endTime) : DAY_MINUTES;
  const bounds =
    drop.edge === 'move'
      ? moved(start, end, drop)
      : boundsOn(
          fields.startDate,
          start,
          clamp(end + drop.minutes, start + SNAP_MINUTES, DAY_MINUTES)
        );
  const unchanged =
    bounds.startDate === fields.startDate &&
    bounds.startTime === fields.startTime &&
    bounds.endDate === fields.endDate &&
    bounds.endTime === fields.endTime;
  return unchanged ? null : { ...fields, ...bounds };
}

function moved(start: number, end: number, drop: EventDrop): WallBounds {
  const length = end - start;
  const landed = clamp(start + drop.minutes, 0, DAY_MINUTES - length);
  return boundsOn(drop.day, landed, landed + length);
}

/**
 * @param event - A timed event's instants.
 * @param zone - The account's zone.
 * @returns Its bounds on the account's wall.
 */
export function wallFieldsOf(event: { start: string; end: string }, zone: string): WallBounds {
  const start = instantToWall(new Date(event.start), zone);
  const end = instantToWall(new Date(event.end), zone);
  return { startDate: start.date, startTime: start.time, endDate: end.date, endTime: end.time };
}
