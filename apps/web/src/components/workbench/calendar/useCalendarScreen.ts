'use client';

/**
 * The calendar screen's small state machines (ADR-369, Task 5.2), each one job:
 *
 * - the ADDRESS: the view, its day and the open event ride the query string —
 *   opening an event pushes, closing and moving replace, so « back » closes
 *   the event rather than leaving the screen;
 * - the DEVICE's choices: the view the screen opens on, and the calendars this
 *   account hides here (`lib/workbench/calendar/preferences`);
 * - the WINDOW: the day alone, the week holding it, the six weeks of its month,
 *   or in the agenda the next `AGENDA_DAYS` from it — a week and a month from the
 *   locale's first weekday;
 * - the ALIAS: the home names the account's own calendar `primary` when no default
 *   was chosen (2026-11-07); the address takes its real id once the calendars are read.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';

import { getIntlLocale, type Language } from '@/i18n/settings';
import { eventKey } from '@/lib/workbench/calendar/events';
import {
  CALENDAR_VIEW_KEY,
  hiddenCalendarsKey,
  parseHidden,
  parseView,
  readCalendarPreference,
  subscribeCalendarPreferences,
  writeCalendarPreference,
  type CalendarView,
} from '@/lib/workbench/calendar/preferences';
import { monthGrid } from '@/lib/workbench/calendar/layout';
import {
  addDays,
  addMonths,
  daysFrom,
  firstWeekday,
  weekStart,
} from '@/lib/workbench/calendar/zoned';
import { toolPath } from '@/lib/workbench/tools';
import type { CalendarEvent, WorkbenchCalendar } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

const WEEK = 7;
/** The days the agenda lists, from the day it stands on (a window is 42 at most). */
export const AGENDA_DAYS = 30;
const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const NO_STORED = () => null;
/** What the providers and the home call the account's own calendar (the connector's fallback). */
export const OWN_CALENDAR_ALIAS = 'primary';

type Query = Partial<Record<'view' | 'day' | 'cal' | 'event', string | null>>;

export interface CalendarAddress {
  view: CalendarView;
  /** The day the view holds. */
  day: string;
  open: { calendarId: string; eventId: string } | null;
  openKey: string | null;
  /** A card may name a calendar alone, without an event to open. */
  selectedCalendarId: string | null;
  /** The days the view shows. */
  days: string[];
  eventHref: (event: Pick<CalendarEvent, 'calendar_id' | 'id'>) => string;
  agendaHref: (day: string) => string;
  /** Moves the view (its day or its kind), keeping no event open. */
  move: (query: Query) => void;
  /** Names the open event anew, in place of the address that named it. */
  reopen: (event: Pick<CalendarEvent, 'calendar_id' | 'id'>) => void;
  close: () => void;
}

/** @returns The days a view shows, around the day it holds. */
function daysOf(view: CalendarView, day: string, firstDay: number): string[] {
  switch (view) {
    case 'month':
      return monthGrid(day, firstDay);
    case 'day':
      return [day];
    case 'agenda':
      return daysFrom(day, AGENDA_DAYS);
    case 'week':
      return daysFrom(weekStart(day, firstDay), WEEK);
  }
}

/**
 * @param lng - The reader's language (its first weekday).
 * @param today - The account's day.
 * @param fallbackView - The view when neither the address nor the device names one.
 */
export function useCalendarAddress(
  lng: Language,
  today: string,
  fallbackView: CalendarView
): CalendarAddress {
  const router = useRouter();
  const params = useSearchParams();
  const stored = useSyncExternalStore(
    subscribeCalendarPreferences,
    () => readCalendarPreference(CALENDAR_VIEW_KEY),
    NO_STORED
  );
  const view = parseView(params.get('view')) ?? parseView(stored) ?? fallbackView;
  const asked = params.get('day');
  const day = asked && DAY_PATTERN.test(asked) ? asked : today;
  const calendarId = params.get('cal');
  const eventId = params.get('event');
  const open = calendarId && eventId ? { calendarId, eventId } : null;
  const firstDay = firstWeekday(getIntlLocale(lng));

  // Plain functions: the React Compiler memoizes them on what they read.
  const hrefOf = (query: Query) => {
    const kept = new URLSearchParams();
    for (const [name, value] of Object.entries(query)) if (value) kept.set(name, value);
    const search = kept.toString();
    return `${buildLocalizedPath(toolPath('calendar'), lng)}${search ? `?${search}` : ''}`;
  };
  const eventHref = (event: Pick<CalendarEvent, 'calendar_id' | 'id'>) =>
    hrefOf({ view, day, cal: event.calendar_id, event: event.id });
  const agendaHref = (target: string) => hrefOf({ view: 'agenda', day: target });
  const move = (query: Query) => {
    if (query.view) writeCalendarPreference(CALENDAR_VIEW_KEY, query.view);
    router.replace(hrefOf({ view, day, ...query, cal: null, event: null }), { scroll: false });
  };
  const close = () => router.replace(hrefOf({ view, day }), { scroll: false });
  const reopen = (event: Pick<CalendarEvent, 'calendar_id' | 'id'>) =>
    router.replace(eventHref(event), { scroll: false });
  return {
    view,
    day,
    open,
    openKey: open ? eventKey({ calendar_id: open.calendarId, id: open.eventId }) : null,
    selectedCalendarId: calendarId && !eventId ? calendarId : null,
    days: daysOf(view, day, firstDay),
    eventHref,
    agendaHref,
    move,
    reopen,
    close,
  };
}

/** Temporarily reveal a card's calendar while preserving the device's hidden set. */
export function calendarSelection(
  address: CalendarAddress,
  calendars: readonly WorkbenchCalendar[],
  preferences: HiddenCalendars
): HiddenCalendars & { target: WorkbenchCalendar | undefined } {
  const wanted = address.selectedCalendarId;
  const target = calendars.find(calendar =>
    wanted === OWN_CALENDAR_ALIAS ? calendar.primary : calendar.id === wanted
  );
  const hidden = new Set(preferences.hidden);
  if (target) hidden.delete(target.id);
  return {
    target,
    hidden,
    toggle: id => {
      // Hiding an already hidden, temporarily revealed target only closes that reveal.
      if (id !== target?.id || !preferences.hidden.has(id)) preferences.toggle(id);
      if (id === target?.id) address.close();
    },
  };
}

/**
 * An event named in the account's own calendar by its alias is named again by that calendar's
 * real id, once the calendars are read: the list, the colour and every act read the real one.
 *
 * @param address - The screen's address.
 * @param calendars - The account's calendars, as read (empty while they are not).
 */
export function useOwnCalendarAlias(
  address: CalendarAddress,
  calendars: readonly WorkbenchCalendar[]
): void {
  const { open, reopen } = address;
  const own = calendars.find(calendar => calendar.primary)?.id;
  const aliased = open?.calendarId === OWN_CALENDAR_ALIAS ? open.eventId : null;
  useEffect(() => {
    if (aliased && own && own !== OWN_CALENDAR_ALIAS) reopen({ calendar_id: own, id: aliased });
  }, [aliased, own, reopen]);
}

/** @returns The day a step moves the view to: as far as the view reaches. */
export function stepDay(view: CalendarView, day: string, steps: number): string {
  if (view === 'month') return addMonths(day, steps);
  const reach = { day: 1, week: WEEK, agenda: AGENDA_DAYS }[view];
  return addDays(day, steps * reach);
}

export interface HiddenCalendars {
  hidden: ReadonlySet<string>;
  toggle: (calendarId: string) => void;
}

/** @param owner - The account (calendar ids are an account's). */
export function useHiddenCalendars(owner: string): HiddenCalendars {
  const key = hiddenCalendarsKey(owner);
  const stored = useSyncExternalStore(
    subscribeCalendarPreferences,
    () => readCalendarPreference(key),
    NO_STORED
  );
  const hidden = useMemo(() => parseHidden(stored), [stored]);
  const toggle = useCallback(
    (calendarId: string) => {
      const next = new Set(hidden);
      if (next.has(calendarId)) next.delete(calendarId);
      else next.add(calendarId);
      writeCalendarPreference(key, JSON.stringify([...next]));
    },
    [hidden, key]
  );
  return { hidden, toggle };
}
