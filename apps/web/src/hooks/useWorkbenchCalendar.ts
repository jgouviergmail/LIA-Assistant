'use client';

/**
 * The calendar screen's reads and acts (ADR-369, Task 5.2).
 *
 * Two reads, two hooks, keyed by what they name (`useWorkbenchItem`): the account's
 * calendars, and the window of the calendars shown over the view's days — so
 * another week or another calendar never answers with the previous one, and a
 * refresh after an act re-reads in place. No calendar shown reads nothing. An
 * act goes through `useApiMutation` and its error is rethrown for the screen
 * to say; a create carries its form's key, the provider's own idempotency
 * (a second press of one form creates nothing). A deletion of an event already
 * gone is the deletion done.
 */
import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { EventChangeBody, NewEventBody } from '@/lib/workbench/calendar/editor';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type {
  CalendarEventDetail,
  CalendarEventsWindow,
  WorkbenchCalendar,
} from '@/lib/workbench/types';

const CALENDARS_PATH = '/workbench/calendar/calendars';
const EVENTS_PATH = '/workbench/calendar/events';
const NO_PARAMS = {};

/** The days a view shows, and the calendars drawn in it. */
export interface CalendarWindowRequest {
  calendarIds: readonly string[];
  /** The first day shown. */
  start: string;
  /** The last day shown (included). */
  end: string;
}

export interface WorkbenchCalendarState {
  window: WorkbenchItemState<CalendarEventsWindow>;
  create: (body: NewEventBody) => Promise<CalendarEventDetail | undefined>;
  update: (body: EventChangeBody) => Promise<CalendarEventDetail | undefined>;
  remove: (calendarId: string, eventId: string, notify?: boolean) => Promise<void>;
}

/** The account's calendars. */
export function useWorkbenchCalendars(): WorkbenchItemState<{ calendars: WorkbenchCalendar[] }> {
  return useWorkbenchItem<{ calendars: WorkbenchCalendar[] }>(CALENDARS_PATH, NO_PARAMS);
}

/** @param request - The view's window; null (or no calendar shown) reads nothing. */
export function useWorkbenchCalendar(
  request: CalendarWindowRequest | null
): WorkbenchCalendarState {
  const reads = request !== null && request.calendarIds.length > 0;
  const params = useMemo(
    () =>
      reads
        ? { calendar_ids: request.calendarIds, start: request.start, end: request.end }
        : NO_PARAMS,
    [reads, request]
  );
  const window = useWorkbenchItem<CalendarEventsWindow>(reads ? EVENTS_PATH : null, params);
  const { refresh } = window;
  const { mutate: post } = useApiMutation<NewEventBody, CalendarEventDetail>({
    method: 'POST',
    componentName: 'WorkbenchCalendar',
  });
  const { mutate: patch } = useApiMutation<EventChangeBody, CalendarEventDetail>({
    method: 'PATCH',
    componentName: 'WorkbenchCalendar',
  });
  const { mutate: del } = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: 'WorkbenchCalendar',
  });

  const create = useCallback(
    async (body: NewEventBody) => {
      const made = await post(EVENTS_PATH, body);
      await refresh();
      return made;
    },
    [post, refresh]
  );

  const update = useCallback(
    async (body: EventChangeBody) => {
      const changed = await patch(EVENTS_PATH, body);
      await refresh();
      return changed;
    },
    [patch, refresh]
  );

  const remove = useCallback(
    async (calendarId: string, eventId: string, notify?: boolean) => {
      const query = { calendar_id: calendarId, event_id: eventId, notify };
      try {
        await del(EVENTS_PATH, undefined, { params: query });
      } catch (error: unknown) {
        if (workbenchRefusal(error)?.key !== 'workbench.errors.item_gone') throw error;
      }
      await refresh();
    },
    [del, refresh]
  );

  return { window, create, update, remove };
}
