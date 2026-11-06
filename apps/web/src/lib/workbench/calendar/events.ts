/**
 * The events a view draws, from a window and the calendars shown (ADR-369).
 *
 * An event id is unique within ITS calendar only (an invitation lives in two),
 * so a drawn event's key is its calendar and its id. Each carries its
 * calendar's colour — data, drawn as it is. A dated task is drawn as a day of its
 * own: it is shown and hidden like a calendar, and opens among the tasks.
 */
import { safeAddress } from '@/lib/text-links';
import type {
  CalendarEvent,
  CalendarEventsWindow,
  DueTasks,
  WorkbenchCalendar,
} from '@/lib/workbench/types';

import { addDays } from './zoned';

/** The dated tasks, as the list of calendars shows and hides them. */
export const DUE_TASKS_LAYER = 'lia:due-tasks';

/** An event as a view draws it: its key and its calendar's colour. */
export interface ShownEvent extends CalendarEvent {
  key: string;
  color: string | null;
  /** The page it opens on, when it is no event of a calendar. */
  href?: string;
}

/** @returns The key of an event: its calendar and its id. */
export function eventKey(event: Pick<CalendarEvent, 'calendar_id' | 'id'>): string {
  return `${event.calendar_id}|${event.id}`;
}

/**
 * The provider's call link is a third party's words, like any address in a text.
 *
 * @param url - What the provider says the call is.
 * @returns The address to follow; null when there is none the page would follow.
 */
export function callHref(url: string | null): string | null {
  const address = url ? safeAddress(url) : null;
  return address && /^https?:/i.test(address.href) ? address.href : null;
}

/**
 * @param due - The tasks read for the days shown.
 * @param label - How a task reads in a view, given its title.
 * @param lng - The page's language, for the address of a task.
 * @returns The tasks as days of their own, each a link into the tasks.
 */
export function shownTasks(
  due: DueTasks | undefined,
  label: (title: string) => string,
  lng: string
): ShownEvent[] {
  return (due?.tasks ?? []).map(task => {
    const params = new URLSearchParams({ list: task.list_id, task: task.id });
    return {
      id: task.id,
      calendar_id: DUE_TASKS_LAYER,
      summary: label(task.title),
      all_day: true,
      start: task.due,
      end: addDays(task.due, 1),
      location: null,
      recurring: false,
      conference_url: null,
      key: `${DUE_TASKS_LAYER}|${task.list_id}|${task.id}`,
      color: null,
      href: `/${lng}/dashboard/tools/tasks?${params}`,
    };
  });
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
