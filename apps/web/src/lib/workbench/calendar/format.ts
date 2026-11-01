/**
 * How the calendar screen says a time (ADR-369), with Intl alone.
 *
 * A DAY (`YYYY-MM-DD`) is formatted in UTC — it is a calendar date, never moved
 * by a zone. An INSTANT is formatted on the account's wall (its zone id). An
 * all-day event's end is exclusive on the wire and its last day INCLUDED when
 * a person reads it.
 */
import { getIntlLocale, type Language } from '@/i18n/settings';
import type { CalendarEvent } from '@/lib/workbench/types';

import { addDays } from './zoned';

function dayDate(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, date));
}

function dayFormat(lng: Language, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat(getIntlLocale(lng), { ...options, timeZone: 'UTC' });
}

/** @returns « lun. 2 nov. » for a day. */
export function shortDay(day: string, lng: Language): string {
  return dayFormat(lng, { weekday: 'short', day: 'numeric', month: 'short' }).format(dayDate(day));
}

/** @returns « lundi 2 novembre » for a day (the agenda's headings). */
export function longDay(day: string, lng: Language): string {
  return dayFormat(lng, { weekday: 'long', day: 'numeric', month: 'long' }).format(dayDate(day));
}

/** @returns « 26 oct. – 1 nov. 2026 » for the days of a view. */
export function rangeLabel(first: string, last: string, lng: Language): string {
  const format = dayFormat(lng, { day: 'numeric', month: 'short', year: 'numeric' });
  return format.formatRange(dayDate(first), dayDate(last));
}

/** @returns « octobre 2026 » for the month holding a day. */
export function monthLabel(day: string, lng: Language): string {
  return dayFormat(lng, { month: 'long', year: 'numeric' }).format(
    dayDate(`${day.slice(0, 7)}-01`)
  );
}

/** @returns « 15:00 » for an instant on the account's wall. */
export function timeLabel(instant: string, zone: string, lng: Language): string {
  return new Intl.DateTimeFormat(getIntlLocale(lng), {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: zone,
  }).format(new Date(instant));
}

/**
 * @param event - The event.
 * @param zone - The account's zone.
 * @param lng - The reader's language.
 * @param allDayLabel - The words « all day », translated.
 * @returns When it takes place, as a person reads it.
 */
export function eventWhen(
  event: Pick<CalendarEvent, 'all_day' | 'start' | 'end'>,
  zone: string,
  lng: Language,
  allDayLabel: string
): string {
  if (event.all_day) {
    const last = addDays(event.end, -1);
    if (last <= event.start) return `${shortDay(event.start, lng)} · ${allDayLabel}`;
    const format = dayFormat(lng, { weekday: 'short', day: 'numeric', month: 'short' });
    return format.formatRange(dayDate(event.start), dayDate(last));
  }
  const day = new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: zone,
  });
  const start = new Date(event.start);
  const end = new Date(event.end);
  if (day.format(start) === day.format(end)) {
    return `${day.format(start)} · ${timeLabel(event.start, zone, lng)} – ${timeLabel(event.end, zone, lng)}`;
  }
  return new Intl.DateTimeFormat(getIntlLocale(lng), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: zone,
  }).formatRange(start, end);
}
