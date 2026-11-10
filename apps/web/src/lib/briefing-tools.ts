/**
 * Where a home card's item opens in the Tools, and the plain links its menu holds (2026-11-07).
 *
 * An item opens on the address its tool already reads (the search's addresses, `search.ts`), so
 * a link from the home works like any link of that tool. An item that lacks what its tool needs —
 * a payload cached before the ids joined it — opens nothing there, and the card keeps the chat.
 *
 * Pure: the cards read it.
 */
import { fallbackLng, isLanguage, type Language } from '@/i18n/settings';
import type {
  AgendaEventItem,
  BirthdayItem,
  DocumentItem,
  MailItem,
  TaskItem,
} from '@/types/briefing';

import { addDays } from './workbench/calendar/zoned';
import { MAIL_INBOX } from './workbench/mail';
import { toolHref } from './workbench/search';
import { dayIn } from './workbench/tasks';
import type { WorkbenchToolId } from './workbench/types';

/** Fewer digits than this is a short code, never a number a phone dials. */
const DIALABLE_MIN_DIGITS = 3;

function address(tool: WorkbenchToolId, lng: Language, query: Record<string, string>): string {
  return `${toolHref(tool, lng)}?${new URLSearchParams(query)}`;
}

/**
 * @param event - An agenda item.
 * @param lng - The page's language.
 * @param zone - The account's zone: the day the calendar opens on is the account's.
 * @returns The event in the calendar, on its day; null without its id, calendar or start.
 */
export function eventHref(
  event: Pick<AgendaEventItem, 'id' | 'calendar_id' | 'start_at'>,
  lng: Language,
  zone: string | undefined
): string | null {
  if (!event.id || !event.calendar_id || !event.start_at) return null;
  const day = dayIn(zone, new Date(event.start_at));
  return address('calendar', lng, { day, cal: event.calendar_id, event: event.id });
}

/** @returns An unread message of the inbox, in the mail tool; null without its id. */
export function mailHref(mail: Pick<MailItem, 'id'>, lng: Language): string | null {
  return mail.id ? address('mail', lng, { folder: MAIL_INBOX, id: mail.id }) : null;
}

/**
 * @returns The task in its own list; without a list it could read, the tool opens its default
 *   one and the task only if it is there. Null without the task's id.
 */
export function taskHref(task: Pick<TaskItem, 'id' | 'list_id'>, lng: Language): string | null {
  if (!task.id) return null;
  return address('tasks', lng, { ...(task.list_id ? { list: task.list_id } : {}), task: task.id });
}

/** @returns The file in the files tool; null without its id. */
export function documentHref(doc: Pick<DocumentItem, 'id'>, lng: Language): string | null {
  return doc.id ? address('files', lng, { file: doc.id }) : null;
}

/** @returns The contact whose birthday it is; null without its id. */
export function birthdayHref(
  birthday: Pick<BirthdayItem, 'contact_id'>,
  lng: Language
): string | null {
  return birthday.contact_id ? address('contacts', lng, { contact: birthday.contact_id }) : null;
}

/** @returns A map asked for the way to `place`, a link every device opens. */
export function directionsHref(place: string): string {
  return `https://www.google.com/maps/dir/?${new URLSearchParams({ api: '1', destination: place })}`;
}

/** @returns The number a phone dials; null for a sender that is a name or a short code. */
export function telHref(number: string): string | null {
  const dialable = number.replace(/[^\d+]/g, '');
  const digits = dialable.replace(/\D/g, '');
  if (digits.length < DIALABLE_MIN_DIGITS || /[A-Za-z]/.test(number)) return null;
  return `tel:${dialable}`;
}

/** @returns The page's language from i18next's (`fr-FR` reads `fr`), else the default. */
export function homeLanguage(raw: string | undefined): Language {
  const candidate = (raw || fallbackLng).split('-')[0];
  return isLanguage(candidate) ? candidate : fallbackLng;
}

/** @returns Tomorrow in the account's zone, `YYYY-MM-DD`: where « postpone » moves a task. */
export function postponedDay(zone: string | undefined, now: Date): string {
  return addDays(dayIn(zone, now), 1);
}
