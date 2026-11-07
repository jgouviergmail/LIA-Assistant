'use client';

/**
 * Where a new event starts (ADR-369): every way of opening the editor on one —
 * « New event », a slot of the grid, an empty part of a month's day, a copy.
 *
 * Each goes to the calendar a new event belongs in, and none is offered where no
 * calendar can be written. A copy stays in its calendar when that one can be
 * written. A new editor mints a new key, so a copy is an event of its own.
 */
import type { CalendarEventDetail, WorkbenchCalendar } from '@/lib/workbench/types';
import type { ProposedEvent } from '@/lib/workbench/assist';
import {
  allDayFields,
  duplicateFields,
  newEventFields,
  withProposedEvent,
} from '@/lib/workbench/calendar/editor';
import { instantToWall } from '@/lib/workbench/calendar/zoned';

import type { EditorTarget } from './EventEditor';

/** Where a new event goes: the settings' default, the account's own, the first it can write. */
function defaultCalendar(calendars: readonly WorkbenchCalendar[]): WorkbenchCalendar | undefined {
  const writable = calendars.filter(calendar => calendar.writable);
  return (
    writable.find(calendar => calendar.default) ??
    writable.find(calendar => calendar.primary) ??
    writable[0]
  );
}

/** The hour a new event starts at: the next one today, nine o'clock another day. */
function startHour(day: string, today: string, zone: string): { day: string; time: string } {
  if (day !== today) return { day, time: '09:00' };
  const now = instantToWall(new Date(Date.now() + 60 * 60 * 1000), zone);
  return { day: now.date, time: `${now.time.slice(0, 2)}:00` };
}

export interface EventStarts {
  /** Some calendar can be written. */
  writable: boolean;
  /** « New event » on a day. */
  startOn: (day: string) => void;
  /** A new event today, on words another tool handed over, or on what LIA read. */
  startWith: (summary: string, description: string, proposal?: ProposedEvent) => void;
  /** Left out where nothing can be written: a slot of the grid (a null time: all day). */
  onSlot?: (day: string, time: string | null) => void;
  /** Left out where nothing can be written: an empty part of a month's day. */
  onDay?: (day: string) => void;
  /** Left out where nothing can be written: a copy of an event. */
  onDuplicate?: (event: CalendarEventDetail) => void;
}

export function eventStarts(
  calendars: readonly WorkbenchCalendar[],
  today: string,
  zone: string,
  compose: (target: EditorTarget) => void
): EventStarts {
  const into = defaultCalendar(calendars);
  if (!into) {
    return { writable: false, startOn: () => undefined, startWith: () => undefined };
  }
  const startOn = (day: string) => {
    const at = startHour(day, today, zone);
    compose({ kind: 'new', fields: newEventFields(into.id, at.day, at.time) });
  };
  return {
    writable: true,
    startOn,
    startWith: (summary, description, proposal) => {
      const at = startHour(today, today, zone);
      const fields = { ...newEventFields(into.id, at.day, at.time), summary, description };
      const filled = proposal ? withProposedEvent(fields, { ...proposal, description }) : fields;
      compose({ kind: 'new', fields: filled });
    },
    onDay: startOn,
    onSlot: (day, time) =>
      compose({
        kind: 'new',
        fields: time === null ? allDayFields(into.id, day) : newEventFields(into.id, day, time),
      }),
    onDuplicate: event => {
      const own = calendars.find(item => item.id === event.calendar_id && item.writable);
      compose({ kind: 'new', fields: duplicateFields(event, zone, (own ?? into).id) });
    },
  };
}
