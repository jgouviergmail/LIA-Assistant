/**
 * Wall time ↔ instant for a zone, with Intl alone (ADR-369, spec §14): the
 * frontend has no date library (F20).
 *
 * The page writes what a clock on the account's wall would read and sends it
 * with the zone's id, never an offset; it reads every instant back on that same
 * wall. A wall minute is mapped by trying the zone's offset just before and
 * just after it: the spring-forward night has a minute neither reaches, which
 * becomes the next minute that exists; the fall-back night has a minute both
 * reach, and the earlier one is taken. Days are counted on the calendar (UTC
 * arithmetic on dates), so a day is never 23 or 25 hours long.
 */

/** @returns The zones a person can pick: the account's first, then the one kept, then all. */
export function zoneChoices(account: string, kept: string | null): string[] {
  // A browser that cannot list them still offers the two that matter.
  const known = Intl.supportedValuesOf?.('timeZone') ?? [];
  return [...new Set([account, ...(kept ? [kept] : []), ...known])];
}

/**
 * The server reads zones with its own table, the page with the browser's, and an unknown
 * one makes `Intl` throw.
 *
 * @returns The zone when this browser can read it; null otherwise.
 */
export function readableZone(zone: string | null): string | null {
  if (zone === null) return null;
  try {
    new Intl.DateTimeFormat('en', { timeZone: zone });
    return zone;
  } catch {
    return null;
  }
}

/** A minute on a wall: its day and its time, as native inputs write them. */
export interface WallTime {
  date: string;
  time: string;
}

const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(zone: string): Intl.DateTimeFormat {
  let found = formatters.get(zone);
  if (!found) {
    found = new Intl.DateTimeFormat('en-CA', {
      timeZone: zone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
    formatters.set(zone, found);
  }
  return found;
}

/** @returns What the zone's wall reads at `instant` (to the minute). */
export function instantToWall(instant: Date, zone: string): WallTime {
  const parts: Record<string, string> = {};
  for (const part of formatter(zone).formatToParts(instant)) parts[part.type] = part.value;
  // An engine may still write midnight as 24 under h23.
  const hour = parts.hour === '24' ? '00' : parts.hour;
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${hour}:${parts.minute}` };
}

/** A wall minute as if it were UTC, in milliseconds — the frame offsets are measured in. */
function asUtc(date: string, time: string): number {
  const [year, month, day] = date.split('-').map(Number);
  const [hour, minute] = time.split(':').map(Number);
  return Date.UTC(year, month - 1, day, hour, minute);
}

function wallMs(instant: number, zone: string): number {
  const wall = instantToWall(new Date(instant), zone);
  return asUtc(wall.date, wall.time);
}

/**
 * @param date - The day, `YYYY-MM-DD`.
 * @param time - The time on the wall, `HH:MM`.
 * @param zone - An IANA zone id.
 * @returns The instant that wall minute is — the next minute that exists when it
 *   does not, the earlier one when it exists twice.
 */
export function wallTimeToInstant(date: string, time: string, zone: string): Date {
  const wanted = asUtc(date, time);
  const before = wallMs(wanted - DAY, zone) - (wanted - DAY);
  const after = wallMs(wanted + DAY, zone) - (wanted + DAY);
  const reached = [wanted - before, wanted - after].filter(at => wallMs(at, zone) === wanted);
  if (reached.length > 0) return new Date(Math.min(...reached));
  // Skipped by the clocks: walk from the earlier guess to the first minute past it.
  const last = Math.max(wanted - before, wanted - after);
  for (let at = Math.min(wanted - before, wanted - after); at <= last; at += MINUTE) {
    if (wallMs(at, zone) >= wanted) return new Date(at);
  }
  return new Date(last);
}

function dayMs(date: string): number {
  return asUtc(date, '00:00');
}

function dateOf(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** @returns `date` moved by `days` calendar days. */
export function addDays(date: string, days: number): string {
  return dateOf(dayMs(date) + days * DAY);
}

/** @returns The first day of the month `months` away from the one holding `date`. */
export function addMonths(date: string, months: number): string {
  const [year, month] = date.split('-').map(Number);
  return dateOf(Date.UTC(year, month - 1 + months, 1));
}

/** @returns `count` days from `first`, in order. */
export function daysFrom(first: string, count: number): string[] {
  return Array.from({ length: count }, (_, index) => addDays(first, index));
}

/** @returns The days from `from` to `to` (negative when `to` comes first). */
export function daysBetween(from: string, to: string): number {
  return Math.round((dayMs(to) - dayMs(from)) / DAY);
}

/** @returns The ISO weekday of a day: 1 Monday … 7 Sunday. */
export function dayOfWeek(date: string): number {
  return new Date(dayMs(date)).getUTCDay() || 7;
}

/** @returns The first day of the week holding `date`, weeks starting on `firstDay` (1-7). */
export function weekStart(date: string, firstDay: number): string {
  return addDays(date, -((dayOfWeek(date) - firstDay + 7) % 7));
}

/** @returns The locale's first weekday (1-7), Monday where the engine cannot say. */
export function firstWeekday(locale: string): number {
  try {
    const found = new Intl.Locale(locale);
    // An engine without the method (it is recent) cannot say.
    return typeof found.getWeekInfo === 'function' ? found.getWeekInfo().firstDay : 1;
  } catch {
    return 1;
  }
}
