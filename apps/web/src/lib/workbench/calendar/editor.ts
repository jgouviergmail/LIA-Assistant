/**
 * The event editor's model (ADR-369, spec §14): pure.
 *
 * The form holds DAYS and WALL TIMES, as native inputs write them; an all-day
 * event's last day is INCLUDED there and EXCLUSIVE on the wire. What leaves is
 * the wall time and the account's zone id, never an offset. A change sends only
 * what moved — the bounds together with whether they are days — so an untouched
 * guest list is never rewritten on someone else's meeting.
 */
import type { CalendarEventDetail } from '@/lib/workbench/types';

import { addDays, instantToWall, wallTimeToInstant } from './zoned';

/** An event to create (`schemas/calendar.NewEvent`): wall times and their zone. */
export interface NewEventBody {
  calendar_id: string;
  summary: string;
  /** A day (all-day) or a wall time `YYYY-MM-DDTHH:MM`. */
  start: string;
  /** A day, EXCLUSIVE (all-day), or a wall time. */
  end: string;
  all_day: boolean;
  /** The zone the wall times are read in (the account's). */
  timezone: string;
  location?: string;
  description?: string;
  attendees?: string[];
  conference?: boolean;
  /** One key per form: the provider creates the event once. */
  idempotency_key: string;
}

/** What changes on one event (an occurrence alone); a field left out is kept. */
export interface EventChangeBody {
  calendar_id: string;
  event_id: string;
  summary?: string;
  start?: string;
  end?: string;
  all_day?: boolean;
  timezone?: string;
  location?: string;
  description?: string;
  attendees?: string[];
  /** Tell the attendees — sent only where the provider lets the page choose. */
  notify?: boolean;
}

/** What the person writes. */
export interface EventFields {
  summary: string;
  calendarId: string;
  allDay: boolean;
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
  location: string;
  description: string;
  /** Guests as typed: addresses separated by commas, semicolons or spaces. */
  attendees: string;
}

/** @returns The fields of a new event on `day`, an hour long from `time`. */
export function newEventFields(calendarId: string, day: string, time: string): EventFields {
  const [hour, minute] = time.split(':').map(Number);
  const endHour = hour + 1;
  const overflows = endHour >= 24;
  return {
    summary: '',
    calendarId,
    allDay: false,
    startDate: day,
    startTime: time,
    endDate: overflows ? addDays(day, 1) : day,
    endTime: `${String(endHour % 24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
    location: '',
    description: '',
    attendees: '',
  };
}

/** @returns The fields an existing event opens on, read on the account's wall. */
export function fieldsOf(event: CalendarEventDetail, zone: string): EventFields {
  const common = {
    summary: event.summary,
    calendarId: event.calendar_id,
    location: event.location ?? '',
    description: event.description ?? '',
    attendees: event.attendees.map(attendee => attendee.email).join(', '),
  };
  if (event.all_day) {
    return {
      ...common,
      allDay: true,
      startDate: event.start,
      startTime: '09:00',
      endDate: addDays(event.end, -1),
      endTime: '10:00',
    };
  }
  const start = instantToWall(new Date(event.start), zone);
  const end = instantToWall(new Date(event.end), zone);
  return {
    ...common,
    allDay: false,
    startDate: start.date,
    startTime: start.time,
    endDate: end.date,
    endTime: end.time,
  };
}

/** @returns Whether the end comes after the start (an all-day event may last one day). */
export function endsAfterStart(fields: EventFields, zone: string): boolean {
  if (fields.allDay) return fields.endDate >= fields.startDate;
  const start = wallTimeToInstant(fields.startDate, fields.startTime, zone).getTime();
  const end = wallTimeToInstant(fields.endDate, fields.endTime, zone).getTime();
  return end > start;
}

function bounds(fields: EventFields): { start: string; end: string; all_day: boolean } {
  return fields.allDay
    ? { start: fields.startDate, end: addDays(fields.endDate, 1), all_day: true }
    : {
        start: `${fields.startDate}T${fields.startTime}`,
        end: `${fields.endDate}T${fields.endTime}`,
        all_day: false,
      };
}

/** @returns The guests as addresses, each once. */
export function guestsOf(text: string): string[] {
  return [...new Set(text.split(/[\s,;]+/).filter(Boolean))];
}

/** @returns The new event's body: wall times, the account's zone, the form's key. */
export function newEventBody(
  fields: EventFields,
  zone: string,
  options: { conference: boolean; idempotencyKey: string }
): NewEventBody {
  const guests = guestsOf(fields.attendees);
  return {
    calendar_id: fields.calendarId,
    summary: fields.summary.trim(),
    ...bounds(fields),
    timezone: zone,
    ...(fields.location.trim() ? { location: fields.location.trim() } : {}),
    ...(fields.description.trim() ? { description: fields.description } : {}),
    ...(guests.length > 0 ? { attendees: guests } : {}),
    ...(options.conference ? { conference: true } : {}),
    idempotency_key: options.idempotencyKey,
  };
}

/** @returns What changed from `initial`, or null when nothing did. */
export function changeBody(
  event: Pick<CalendarEventDetail, 'calendar_id' | 'id'>,
  initial: EventFields,
  fields: EventFields,
  zone: string,
  notify: boolean | undefined
): EventChangeBody | null {
  const change: EventChangeBody = { calendar_id: event.calendar_id, event_id: event.id };
  const was = bounds(initial);
  const now = bounds(fields);
  if (was.start !== now.start || was.end !== now.end || was.all_day !== now.all_day) {
    Object.assign(change, now, { timezone: zone });
  }
  if (fields.summary.trim() !== initial.summary) change.summary = fields.summary.trim();
  if (fields.location.trim() !== initial.location) change.location = fields.location.trim();
  if (fields.description !== initial.description) change.description = fields.description;
  const guests = guestsOf(fields.attendees);
  if (guests.join(',') !== guestsOf(initial.attendees).join(',')) change.attendees = guests;
  if (Object.keys(change).length === 2) return null;
  return notify === undefined ? change : { ...change, notify };
}
