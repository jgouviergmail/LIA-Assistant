/**
 * The events a view draws, from a window and the calendars shown (ADR-369).
 *
 * An event id is unique within ITS calendar only (an invitation lives in two),
 * so a drawn event's key is its calendar and its id. Each carries its
 * calendar's colour — data, drawn as it is.
 */
import type { CalendarEvent, CalendarEventsWindow, WorkbenchCalendar } from '@/lib/workbench/types';

/** An event as a view draws it: its key and its calendar's colour. */
export interface ShownEvent extends CalendarEvent {
  key: string;
  color: string | null;
}

/** @returns The key of an event: its calendar and its id. */
export function eventKey(event: Pick<CalendarEvent, 'calendar_id' | 'id'>): string {
  return `${event.calendar_id}|${event.id}`;
}

/** @returns Every event of the window, in its calendar's colour, ordered by start. */
export function shownEvents(
  window: CalendarEventsWindow | undefined,
  calendars: readonly WorkbenchCalendar[]
): ShownEvent[] {
  const colours = new Map(calendars.map(calendar => [calendar.id, calendar.color]));
  return (window?.calendars ?? [])
    .flatMap(entry =>
      entry.events.map(event => ({
        ...event,
        key: eventKey(event),
        color: colours.get(entry.calendar_id) ?? null,
      }))
    )
    .sort((a, b) => a.start.localeCompare(b.start));
}
