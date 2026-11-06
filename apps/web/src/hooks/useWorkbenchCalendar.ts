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
import apiClient from '@/lib/api-client';
import type { EventChangeBody, NewEventBody } from '@/lib/workbench/calendar/editor';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type {
  CalendarEventDetail,
  EventAnswer,
  CalendarEventsWindow,
  DueTasks,
  WorkbenchCalendar,
} from '@/lib/workbench/types';
import { generateUUID } from '@/lib/utils';

const CALENDARS_PATH = '/workbench/calendar/calendars';
const EVENTS_PATH = '/workbench/calendar/events';
const EVENT_PATH = '/workbench/calendar/event';
const ANSWER_PATH = '/workbench/calendar/events/answer';
const MOVE_PATH = '/workbench/calendar/events/move';
const DUE_TASKS_PATH = '/workbench/tasks/due';
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
  /** One event, whole: what a drop must know before it acts. */
  read: (calendarId: string, eventId: string) => Promise<CalendarEventDetail>;
  create: (body: NewEventBody) => Promise<CalendarEventDetail | undefined>;
  update: (body: EventChangeBody) => Promise<CalendarEventDetail | undefined>;
  remove: (
    calendarId: string,
    eventId: string,
    notify?: boolean,
    series?: boolean
  ) => Promise<void>;
  /** Answers an invitation, the organiser told; the window is read again. */
  answer: (calendarId: string, eventId: string, response: EventAnswer) => Promise<void>;
  /** Sends an event to another calendar; the window is read again, whatever came of it. */
  move: (calendarId: string, eventId: string, destinationId: string) => Promise<void>;
}

/** Calendars of the person's own: each act rejects when refused, and reads them again. */
export interface CalendarManagement {
  create: (name: string) => Promise<void>;
  rename: (calendarId: string, name: string) => Promise<void>;
  remove: (calendarId: string) => Promise<void>;
}

/**
 * @param start - The first day shown.
 * @param end - The last day shown (included).
 * @param shown - Whether the tasks are drawn: otherwise nothing is read.
 * @returns The open tasks due over those days, from every list.
 */
export function useDueTasks(
  start: string,
  end: string,
  shown: boolean
): WorkbenchItemState<DueTasks> {
  return useWorkbenchItem<DueTasks>(shown ? DUE_TASKS_PATH : null, { start, end });
}

/** @param reread - Reads the calendars, and the window they draw, again. */
export function useCalendarManagement(reread: () => Promise<void>): CalendarManagement {
  const { mutate: post } = useApiMutation<Record<string, string>, void>({
    method: 'POST',
    componentName: 'WorkbenchCalendar',
  });
  const { mutate: patch } = useApiMutation<Record<string, string>, void>({
    method: 'PATCH',
    componentName: 'WorkbenchCalendar',
  });
  const { mutate: del } = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'WorkbenchCalendar',
  });
  const create = useCallback(
    async (name: string) => {
      await post(CALENDARS_PATH, { name, idempotency_key: generateUUID() });
      await reread();
    },
    [post, reread]
  );
  const rename = useCallback(
    async (calendarId: string, name: string) => {
      await patch(CALENDARS_PATH, { calendar_id: calendarId, name });
      await reread();
    },
    [patch, reread]
  );
  const remove = useCallback(
    async (calendarId: string) => {
      await del(CALENDARS_PATH, undefined, { params: { calendar_id: calendarId } });
      await reread();
    },
    [del, reread]
  );
  return useMemo(() => ({ create, rename, remove }), [create, rename, remove]);
}

/** @param open - The event the address names; null reads nothing. */
export function useOpenEvent(
  open: { calendarId: string; eventId: string } | null
): WorkbenchItemState<CalendarEventDetail> {
  return useWorkbenchItem<CalendarEventDetail>(open ? EVENT_PATH : null, {
    calendar_id: open?.calendarId,
    event_id: open?.eventId,
  });
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
  const { mutate: postAnswer } = useApiMutation<Record<string, string>, void>({
    method: 'POST',
    componentName: 'WorkbenchCalendar',
  });

  const read = useCallback(
    (calendarId: string, eventId: string) =>
      apiClient.get<CalendarEventDetail>(EVENT_PATH, {
        params: { calendar_id: calendarId, event_id: eventId },
      }),
    []
  );

  const answer = useCallback(
    async (calendarId: string, eventId: string, response: EventAnswer) => {
      await postAnswer(ANSWER_PATH, { calendar_id: calendarId, event_id: eventId, response });
      await refresh();
    },
    [postAnswer, refresh]
  );

  const move = useCallback(
    async (calendarId: string, eventId: string, destinationId: string) => {
      const asked = {
        calendar_id: calendarId,
        event_id: eventId,
        destination_id: destinationId,
      };
      try {
        await postAnswer(MOVE_PATH, asked);
      } finally {
        await refresh();
      }
    },
    [postAnswer, refresh]
  );

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
    async (calendarId: string, eventId: string, notify?: boolean, series?: boolean) => {
      const query = {
        calendar_id: calendarId,
        event_id: eventId,
        notify,
        ...(series ? { scope: 'series' } : {}),
      };
      try {
        await del(EVENTS_PATH, undefined, { params: query });
      } catch (error: unknown) {
        if (workbenchRefusal(error)?.key !== 'workbench.errors.item_gone') throw error;
      }
      await refresh();
    },
    [del, refresh]
  );

  return { window, read, create, update, remove, answer, move };
}
