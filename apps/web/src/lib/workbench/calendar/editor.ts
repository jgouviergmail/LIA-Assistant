/**
 * The event editor's model (ADR-369, spec §14): pure.
 *
 * The form holds DAYS and WALL TIMES, as native inputs write them; an all-day
 * event's last day is INCLUDED there and EXCLUSIVE on the wire. What leaves is
 * the wall time and its zone's id, never an offset: the account's, unless the
 * person chose another or the event was set in one. A change sends only what
 * moved — the bounds together with whether they are days, and their zone — so an
 * untouched guest list is never rewritten on someone else's meeting. A rule is the
 * one every recurrence of LIA is, anchored here on the event's own first day; it
 * goes on a new event or on a whole series, never on one occurrence.
 */
import { emptyRecurrence, withFreq } from '@/lib/recurrence';
import type { ProposedEvent } from '@/lib/workbench/assist';
import type { CalendarEventDetail } from '@/lib/workbench/types';
import type { RecurrenceSpec } from '@/types/recurrence';

import { addDays, instantToWall, readableZone, wallTimeToInstant } from './zoned';

/** An event to create (`schemas/calendar.NewEvent`): wall times and their zone. */
export interface NewEventBody {
  calendar_id: string;
  summary: string;
  /** A day (all-day) or a wall time `YYYY-MM-DDTHH:MM`. */
  start: string;
  /** A day, EXCLUSIVE (all-day), or a wall time. */
  end: string;
  all_day: boolean;
  /** The zone the wall times are read in. */
  timezone: string;
  location?: string;
  description?: string;
  attendees?: string[];
  conference?: boolean;
  /** A reminder this long before; left out, the calendar's own. */
  reminder_minutes?: number;
  busy?: boolean;
  private?: boolean;
  /** When it happens again. */
  recurrence?: RecurrenceSpec;
  /** One key per form: the provider creates the event once. */
  idempotency_key: string;
}

/** What changes on one event (an occurrence alone unless `scope` says); a field left out is kept. */
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
  /** A new reminder; `NO_REMINDER` takes it off. */
  reminder_minutes?: number;
  busy?: boolean;
  private?: boolean;
  /** Adds a video call to an event that has none. */
  conference?: boolean;
  /** Tell the attendees — sent only where the provider lets the page choose. */
  notify?: boolean;
  /** The whole series, rather than this occurrence. */
  scope?: 'series';
  /** A new rule for the whole series. */
  recurrence?: RecurrenceSpec;
}

/** « No reminder » on the wire; left out, a reminder is kept. */
export const NO_REMINDER = -1;
/** The reminders the form offers, in minutes before. */
export const REMINDER_CHOICES: readonly number[] = [0, 5, 10, 15, 30, 60, 120, 1440];

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
  /** Minutes before, `NO_REMINDER`, or null for the calendar's own. */
  reminder: number | null;
  busy: boolean;
  private: boolean;
  /** The clock the times are on; null for the account's. */
  zone: string | null;
  /** When it happens again; `once` for an event that does not. */
  repeat: RecurrenceSpec;
}

/** @returns The rule of an event that does not repeat, as the editor opens on it. */
export function noRepeat(day: string): RecurrenceSpec {
  return withFreq(emptyRecurrence(day), 'once');
}

/** @returns The rule as it leaves, from the event's own first day; null when it does not repeat. */
export function ruleOf(fields: EventFields): RecurrenceSpec | null {
  return fields.repeat.freq === 'once' ? null : { ...fields.repeat, anchor_date: fields.startDate };
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
    reminder: null,
    busy: true,
    private: false,
    zone: null,
    repeat: noRepeat(day),
  };
}

/** @returns The fields of a new all-day event, one day long. */
export function allDayFields(calendarId: string, day: string): EventFields {
  return { ...newEventFields(calendarId, day, '09:00'), allDay: true, endDate: day };
}

/**
 * An event LIA read, in the form (ADR-372): the person checks it there and saves it, or not.
 *
 * What it could not read stays as the form holds it, so a day never turns into today by itself.
 *
 * @param fields - What the form holds.
 * @param event - What was read.
 * @returns The form, filled.
 */
export function withProposedEvent(fields: EventFields, event: ProposedEvent): EventFields {
  const startDate = event.start_date ?? fields.startDate;
  const startTime = event.start_time ?? fields.startTime;
  const hourLong = newEventFields(fields.calendarId, startDate, startTime);
  const timed = event.end_date !== null && event.end_time !== null;
  const endDate = timed || event.all_day ? (event.end_date ?? startDate) : hourLong.endDate;
  return {
    ...fields,
    summary: event.summary || fields.summary,
    allDay: event.all_day,
    startDate,
    startTime,
    endDate,
    endTime: timed && event.end_time !== null ? event.end_time : hourLong.endTime,
    location: event.location || fields.location,
    description: event.description || fields.description,
    attendees: event.attendees.join(', ') || fields.attendees,
    repeat:
      event.repeat === 'none'
        ? { ...fields.repeat, anchor_date: startDate }
        : withFreq(emptyRecurrence(startDate), event.repeat),
  };
}

/** @returns The fields an existing event opens on, read on the account's wall. */
export function fieldsOf(event: CalendarEventDetail, zone: string): EventFields {
  const common = {
    repeat: noRepeat(event.start.slice(0, 10)),
    summary: event.summary,
    calendarId: event.calendar_id,
    location: event.location ?? '',
    description: event.description ?? '',
    attendees: event.attendees.map(attendee => attendee.email).join(', '),
    reminder: event.reminder_minutes,
    busy: event.busy,
    private: event.private,
    zone: null,
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

/** @returns What the form opens on: the clock the event was set on, when it has its own. */
export function editorFieldsOf(event: CalendarEventDetail, zone: string): EventFields {
  const own = readableZone(event.zone);
  if (event.all_day || own === null || own === zone) return fieldsOf(event, zone);
  return { ...fieldsOf(event, own), zone: own };
}

/** @returns What a copy of an event opens on, in the calendar it goes to. */
export function duplicateFields(
  event: CalendarEventDetail,
  zone: string,
  calendarId: string
): EventFields {
  return { ...fieldsOf(event, zone), calendarId };
}

/** @returns Whether the end comes after the start (an all-day event may last one day). */
export function endsAfterStart(fields: EventFields, zone: string): boolean {
  if (fields.allDay) return fields.endDate >= fields.startDate;
  const clock = fields.zone ?? zone;
  const start = wallTimeToInstant(fields.startDate, fields.startTime, clock).getTime();
  const end = wallTimeToInstant(fields.endDate, fields.endTime, clock).getTime();
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

/** @returns The new event's body: wall times, their zone, the form's key. */
export function newEventBody(
  fields: EventFields,
  zone: string,
  options: { conference: boolean; idempotencyKey: string }
): NewEventBody {
  const guests = guestsOf(fields.attendees);
  const rule = ruleOf(fields);
  return {
    calendar_id: fields.calendarId,
    summary: fields.summary.trim(),
    ...bounds(fields),
    ...(rule ? { recurrence: rule } : {}),
    timezone: fields.zone ?? zone,
    ...(fields.location.trim() ? { location: fields.location.trim() } : {}),
    ...(fields.description.trim() ? { description: fields.description } : {}),
    ...(guests.length > 0 ? { attendees: guests } : {}),
    ...(options.conference ? { conference: true } : {}),
    ...(fields.reminder === null ? {} : { reminder_minutes: fields.reminder }),
    ...(fields.busy ? {} : { busy: false }),
    ...(fields.private ? { private: true } : {}),
    idempotency_key: options.idempotencyKey,
  };
}

/** What changed beyond the event's time. */
function optionChanges(initial: EventFields, fields: EventFields): Partial<EventChangeBody> {
  return {
    ...(fields.reminder === initial.reminder
      ? {}
      : { reminder_minutes: fields.reminder ?? NO_REMINDER }),
    ...(fields.busy === initial.busy ? {} : { busy: fields.busy }),
    ...(fields.private === initial.private ? {} : { private: fields.private }),
  };
}

/** The new time and the zone it is read on, when either moved. */
function timeChanges(
  initial: EventFields,
  fields: EventFields,
  zone: string
): Partial<EventChangeBody> {
  const was = bounds(initial);
  const now = bounds(fields);
  const moved = was.start !== now.start || was.end !== now.end || was.all_day !== now.all_day;
  return moved || (!fields.allDay && fields.zone !== initial.zone)
    ? { ...now, timezone: fields.zone ?? zone }
    : {};
}

/** What changed in what the event says, and in who comes. */
function contentChanges(initial: EventFields, fields: EventFields): Partial<EventChangeBody> {
  const summary = fields.summary.trim();
  const location = fields.location.trim();
  const guests = guestsOf(fields.attendees);
  return {
    ...(summary === initial.summary ? {} : { summary }),
    ...(location === initial.location ? {} : { location }),
    ...(fields.description === initial.description ? {} : { description: fields.description }),
    ...(guests.join(',') === guestsOf(initial.attendees).join(',') ? {} : { attendees: guests }),
  };
}

/** @returns What changed from `initial`, or null when nothing did. */
export function changeBody(
  event: Pick<CalendarEventDetail, 'calendar_id' | 'id'>,
  initial: EventFields,
  fields: EventFields,
  zone: string,
  notify: boolean | undefined,
  conference = false,
  series = false
): EventChangeBody | null {
  const rule = series ? ruleOf(fields) : null;
  const change: EventChangeBody = {
    calendar_id: event.calendar_id,
    event_id: event.id,
    ...timeChanges(initial, fields, zone),
    ...contentChanges(initial, fields),
    ...optionChanges(initial, fields),
    ...(conference ? { conference: true } : {}),
    ...(rule ? { recurrence: rule, timezone: fields.zone ?? zone } : {}),
  };
  if (Object.keys(change).length === 2) return null;
  if (series) change.scope = 'series';
  return notify === undefined ? change : { ...change, notify };
}
