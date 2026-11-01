/**
 * The mail screen's model (ADR-369, Task 4.7): pure, read by the screen.
 *
 * A listing's params say only what was asked (nothing for an empty box or an
 * unpressed chip, so the address and the request stay short); a period is a
 * range of the ACCOUNT's days, the last one included on screen and excluded
 * on the wire (`before` is the first day NOT included, `schemas/mail.py`); a
 * row's date reads against the account's today, in its zone; an act on a
 * selection is told as it went — never all-or-nothing. The list density is a
 * per-device preference kept in `localStorage` (every access wrapped: a
 * private window simply starts comfortable), outside the account purge.
 */
import { apiEndpointUrl, type QueryParamValue } from '@/lib/api-client';
import { getIntlLocale, type Language } from '@/i18n/settings';

import { dayIn } from './tasks';
import type { WorkbenchActOutcome, MailAddress, MailAttachment } from './types';

/** The folder a listing opens on when the address names none. */
export const MAIL_INBOX = 'system:inbox';
/** The drafts' place: listed by the drafts route where the provider keeps drafts. */
export const MAIL_DRAFTS = 'system:drafts';

/**
 * How long an unread message stays open before the screen marks it read: a
 * glance (a message opened by mistake and closed) leaves it unread.
 */
export const MAIL_READ_DWELL_MS = 1000;

/** The period chip's choices: the last N days up to today, or two chosen days. */
export type MailPeriod = 'any' | 'week' | 'month' | 'year' | 'custom';

/** What narrows a listing besides its folder. */
export interface MailSearch {
  /** The person's words (Gmail-style syntax). */
  q: string;
  unread: boolean;
  attachments: boolean;
  period: MailPeriod;
  /** A chosen range's first and last days (`YYYY-MM-DD`, both included; '' = open). */
  from: string;
  to: string;
}

export const EMPTY_MAIL_SEARCH: MailSearch = {
  q: '',
  unread: false,
  attachments: false,
  period: 'any',
  from: '',
  to: '',
};

/** How many days « the last week / month / year » reaches back, today included. */
const PERIOD_DAYS: Readonly<Record<'week' | 'month' | 'year', number>> = {
  week: 7,
  month: 30,
  year: 365,
};

const DAY_MS = 24 * 60 * 60 * 1000;

/** A `YYYY-MM-DD` day moved by whole calendar days (never by a clock's hours). */
export function addDays(day: string, days: number): string {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, date) + days * DAY_MS).toISOString().slice(0, 10);
}

/** The first day included and the first day NOT included of a period. */
function periodRange(search: MailSearch, today: string): { after?: string; before?: string } {
  if (search.period === 'any') return {};
  if (search.period === 'custom') {
    return {
      after: search.from || undefined,
      before: search.to ? addDays(search.to, 1) : undefined,
    };
  }
  return { after: addDays(today, 1 - PERIOD_DAYS[search.period]) };
}

/**
 * @param folder - The pane's folder id.
 * @param search - What narrows it.
 * @param today - Today in the account's zone (`dayIn`).
 * @returns The listing's params (`schemas/mail.MailListing`), undefined dropped.
 */
export function listingParams(
  folder: string,
  search: MailSearch,
  today: string
): Record<string, QueryParamValue> {
  const words = search.q.trim();
  const { after, before } = periodRange(search, today);
  const params: Record<string, QueryParamValue> = { folder };
  if (words) params.q = words;
  if (search.unread) params.unread = true;
  if (search.attachments) params.attachments = true;
  if (after) params.after = after;
  if (before) params.before = before;
  return params;
}

/** Whole days between two `YYYY-MM-DD` days. */
function daysBetween(earlier: string, later: string): number {
  return Math.round((Date.parse(later) - Date.parse(earlier)) / DAY_MS);
}

/**
 * When a row was received, as the list tells it: its time today, « yesterday »,
 * its weekday this week, its day this year, its date before.
 *
 * @param iso - The instant (UTC); null or unreadable draws nothing.
 * @param now - The instant read as now.
 * @param zone - The account's zone (its days are the ones told).
 * @param lng - The reader's language.
 */
export function receivedLabel(
  iso: string | null,
  now: Date,
  zone: string | undefined,
  lng: Language
): string | null {
  const instant = iso ? new Date(iso) : null;
  if (!instant || Number.isNaN(instant.getTime())) return null;
  const locale = getIntlLocale(lng);
  const day = dayIn(zone, instant);
  const age = daysBetween(day, dayIn(zone, now));
  const format = (options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(locale, { ...options, timeZone: zone }).format(instant);
  if (age <= 0) return format({ hour: '2-digit', minute: '2-digit' });
  if (age === 1) return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(-1, 'day');
  if (age < 7) return format({ weekday: 'short' });
  if (day.slice(0, 4) === dayIn(zone, now).slice(0, 4)) {
    return format({ day: 'numeric', month: 'short' });
  }
  return format({ day: '2-digit', month: '2-digit', year: 'numeric' });
}

/** How an act on a selection went. */
export interface ActReport {
  tone: 'success' | 'partial' | 'failed';
  done: number;
  failed: number;
}

export function actReport(outcome: WorkbenchActOutcome): ActReport {
  const done = outcome.done.length;
  const failed = outcome.failed.length;
  const tone = failed === 0 ? 'success' : done === 0 ? 'failed' : 'partial';
  return { tone, done, failed };
}

/** Whether every, some or none of the messages carry a label (a menu's check). */
export function labelState(
  messages: readonly { label_ids: readonly string[] }[],
  labelId: string
): 'all' | 'some' | 'none' {
  const carrying = messages.filter(message => message.label_ids.includes(labelId)).length;
  if (carrying === 0) return 'none';
  return carrying === messages.length ? 'all' : 'some';
}

/** A sender's initials for the avatar: from the name, else the address, else none. */
export function initials(address: MailAddress | null): string {
  if (!address) return '';
  const words = address.name.replace(/["',]/g, ' ').trim().split(/\s+/).filter(Boolean);
  if (words.length > 0) {
    return words
      .slice(0, 2)
      .map(word => word[0].toUpperCase())
      .join('');
  }
  return address.address.slice(0, 1).toUpperCase();
}

const KIBIBYTE = 1024;

/** A size in the reader's language and unit (« 182 ko », « 182 kB »). */
export function fileSize(bytes: number, lng: Language): string {
  const locale = getIntlLocale(lng);
  const unit = (value: number, name: string, digits: number) =>
    new Intl.NumberFormat(locale, {
      style: 'unit',
      unit: name,
      unitDisplay: 'short',
      maximumFractionDigits: digits,
    }).format(value);
  if (bytes < KIBIBYTE) return unit(bytes, 'byte', 0);
  if (bytes < KIBIBYTE * KIBIBYTE) return unit(Math.round(bytes / KIBIBYTE), 'kilobyte', 0);
  return unit(bytes / (KIBIBYTE * KIBIBYTE), 'megabyte', 1);
}

/** The download of one attachment, through the API's origin (never a relative path). */
export function attachmentUrl(messageId: string, attachment: MailAttachment): string {
  const query = new URLSearchParams({ message_id: messageId });
  if (attachment.id) query.set('attachment_id', attachment.id);
  query.set('filename', attachment.filename);
  return apiEndpointUrl(`/workbench/mail/attachment?${query.toString()}`);
}

/** A mailbox as a header names it: its name, else its address. */
export function addressLabel(address: MailAddress): string {
  return address.name || address.address;
}

/** How tightly the list draws its rows, per device. */
export type MailDensity = 'comfortable' | 'compact';

const DENSITY_KEY = 'lia_workbench_mail_density';
/** Dispatched on `window` after every change, for `useSyncExternalStore`. */
const DENSITY_EVENT = 'lia:workbench-mail-density';

/** This device's choice; comfortable when none is stored or storage is refused. */
export function readMailDensity(): MailDensity {
  try {
    return window.localStorage.getItem(DENSITY_KEY) === 'compact' ? 'compact' : 'comfortable';
  } catch {
    return 'comfortable';
  }
}

/** Remembers this device's choice (a refused storage keeps it for the page only). */
export function writeMailDensity(density: MailDensity): void {
  try {
    window.localStorage.setItem(DENSITY_KEY, density);
  } catch {
    // Storage unavailable (private window, blocked site data): nothing to keep.
  }
  window.dispatchEvent(new Event(DENSITY_EVENT));
}

/** Calls `onChange` after every change of the density, here or in another tab. */
export function subscribeMailDensity(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === DENSITY_KEY) onChange();
  };
  window.addEventListener(DENSITY_EVENT, onChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(DENSITY_EVENT, onChange);
    window.removeEventListener('storage', onStorage);
  };
}
