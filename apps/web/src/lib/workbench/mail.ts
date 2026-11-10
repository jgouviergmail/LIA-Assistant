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

import type { ProposedSearch } from './assist';
import { dayIn } from './tasks';
import type {
  MailAddress,
  MailAttachment,
  MailFolder,
  MailSummary,
  WorkbenchActOutcome,
} from './types';

/** The folder a listing opens on when the address names none. */
export const MAIL_INBOX = 'system:inbox';
/** The drafts' place: listed by the drafts route where the provider keeps drafts. */
export const MAIL_DRAFTS = 'system:drafts';
export const MAIL_SENT = 'system:sent';
export const MAIL_TRASH = 'system:trash';
export const MAIL_SPAM = 'system:spam';
export const MAIL_ARCHIVE = 'system:archive';
const SYSTEM_PREFIX = 'system:';
/** The system places a message sits in; every other one is a view of what sits elsewhere. */
const PLACES: readonly string[] = [MAIL_INBOX, MAIL_ARCHIVE, MAIL_SPAM, MAIL_TRASH];

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

/**
 * @param proposal - The criteria read from the person's sentence.
 * @param attachmentsOffered - The provider filters on attachments.
 * @returns The search they amount to: what a provider cannot carry is left off.
 */
export function proposedMailSearch(
  proposal: ProposedSearch,
  attachmentsOffered: boolean
): MailSearch {
  const dated = Boolean(proposal.first_day || proposal.last_day);
  return {
    q: proposal.words,
    unread: proposal.unread,
    attachments: proposal.attachments && attachmentsOffered,
    period: dated ? 'custom' : 'any',
    from: proposal.first_day ?? '',
    to: proposal.last_day ?? '',
  };
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

/** How many of its own images a message asks for: the API's published bound. */
const INLINE_IMAGES_MAX = 30;
/** One class of characters after the scheme: a hostile page stays linear. */
const CID = /cid:([^\s"'<>)]+)/gi;

function decoded(name: string): string {
  try {
    return decodeURIComponent(name);
  } catch {
    return name;
  }
}

/** @returns The names of the images an HTML body says it carries, as their headers spell them. */
export function cidsOf(html: string): string[] {
  const names = new Set(Array.from(html.matchAll(CID), match => decoded(match[1])));
  return [...names].slice(0, INLINE_IMAGES_MAX);
}

/**
 * @param rows - The listing, in its order.
 * @param id - The message leaving it.
 * @returns What takes its place: the row below, else the row above, else nothing.
 */
export function nextAfter<T extends { id: string }>(rows: readonly T[], id: string): T | null {
  const at = rows.findIndex(row => row.id === id);
  if (at < 0) return null;
  return rows[at + 1] ?? rows[at - 1] ?? null;
}

/** One of the person's folders in its place. */
export interface FolderNode {
  folder: MailFolder;
  /** What is drawn: what lies below its nearest parent, the whole name without one. */
  name: string;
  /** How far under the top; only a parent that exists counts. */
  depth: number;
}

const PATH_SEPARATOR = '/';

function pathOrder(language: Language): (a: string[], b: string[]) => number {
  const collator = new Intl.Collator(getIntlLocale(language), { sensitivity: 'base' });
  return (a, b) => {
    const shared = Math.min(a.length, b.length);
    for (let index = 0; index < shared; index += 1) {
      const order = collator.compare(a[index] ?? '', b[index] ?? '');
      if (order !== 0) return order;
    }
    return a.length - b.length;
  };
}

/**
 * Folders are named by their path (`Clients/Acme`): Gmail and iCloud spell it so,
 * the API walks Graph's. A slash in a label whose parent does not exist is only
 * a character of its name, so nothing is indented under a place that is not there.
 *
 * @param folders - The person's own folders.
 * @param language - The reader's.
 * @returns Each under its parent, siblings in the reader's order.
 */
export function folderTree(folders: readonly MailFolder[], language: Language): FolderNode[] {
  const order = pathOrder(language);
  const paths = folders.map(folder => ({
    folder,
    segments: (folder.name ?? '').split(PATH_SEPARATOR),
  }));
  paths.sort((a, b) => order(a.segments, b.segments));

  const depths = new Map<string, number>();
  return paths.map(({ folder, segments }) => {
    for (let cut = segments.length - 1; cut > 0; cut -= 1) {
      const parent = depths.get(segments.slice(0, cut).join(PATH_SEPARATOR));
      if (parent !== undefined) {
        depths.set(segments.join(PATH_SEPARATOR), parent + 1);
        return { folder, name: segments.slice(cut).join(PATH_SEPARATOR), depth: parent + 1 };
      }
    }
    depths.set(segments.join(PATH_SEPARATOR), 0);
    return { folder, name: segments.join(PATH_SEPARATOR), depth: 0 };
  });
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

/**
 * @param iso - When the mailbox received it (ISO, UTC).
 * @param zone - The account's zone: its day and hour are the ones told.
 * @param lng - The reader's language.
 * @returns Its day and hour as the reader reads them; empty when there is none to tell.
 */
export function receivedFull(iso: string | null, zone: string | undefined, lng: Language): string {
  if (!iso) return '';
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return '';
  return new Intl.DateTimeFormat(getIntlLocale(lng), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: zone,
  }).format(instant);
}

/** A two-way choice kept on this device, for `useSyncExternalStore`. */
interface DeviceChoice<T extends string> {
  /** This device's choice; the usual one when none is stored or storage is refused. */
  read: () => T;
  /** Remembers it (a refused storage keeps it for the page only). */
  write: (choice: T) => void;
  /** Calls `onChange` after every change, here or in another tab. */
  subscribe: (onChange: () => void) => () => void;
}

function deviceChoice<T extends string>(key: string, usual: T, other: T): DeviceChoice<T> {
  const changed = `${key}:changed`;
  return {
    read: () => {
      try {
        return window.localStorage.getItem(key) === other ? other : usual;
      } catch {
        return usual;
      }
    },
    write: choice => {
      try {
        window.localStorage.setItem(key, choice);
      } catch {
        // Storage unavailable (private window, blocked site data): nothing to keep.
      }
      window.dispatchEvent(new Event(changed));
    },
    subscribe: onChange => {
      const onStorage = (event: StorageEvent) => {
        if (event.key === key) onChange();
      };
      window.addEventListener(changed, onChange);
      window.addEventListener('storage', onStorage);
      return () => {
        window.removeEventListener(changed, onChange);
        window.removeEventListener('storage', onStorage);
      };
    },
  };
}

/** How tightly the list draws its rows, per device. */
export type MailDensity = 'comfortable' | 'compact';

const density = deviceChoice<MailDensity>('lia_workbench_mail_density', 'comfortable', 'compact');
export const readMailDensity = density.read;
export const writeMailDensity = density.write;
export const subscribeMailDensity = density.subscribe;

/** Whether the list draws a conversation as one line, per device. */
export type MailGrouping = 'flat' | 'grouped';

const grouping = deviceChoice<MailGrouping>('lia_workbench_mail_grouping', 'flat', 'grouped');
export const readMailGrouping = grouping.read;
export const writeMailGrouping = grouping.write;
export const subscribeMailGrouping = grouping.subscribe;

/** One line of the list: a message, or a conversation under its newest message. */
export interface MailLine {
  /** What the line shows; its id names the line. */
  message: MailSummary;
  /** The messages it stands for, as far as they are loaded, in the listing's order. */
  members: readonly MailSummary[];
}

/** A conversation's line: its newest message, with what any of them says. */
function conversationLine(members: readonly MailSummary[]): MailLine {
  return {
    message: {
      ...members[0],
      is_read: members.every(member => member.is_read),
      is_starred: members.some(member => member.is_starred),
      has_attachments: members.some(member => member.has_attachments),
      label_ids: [...new Set(members.flatMap(member => member.label_ids))],
    },
    members,
  };
}

/**
 * @param rows - What is loaded, in the listing's order (the newest first).
 * @param grouped - A conversation is one line.
 * @returns The lines, by what is LOADED: a conversation gathers more as the list grows, so no
 * line claims how many messages it holds (ADR-185).
 */
export function mailLines(rows: readonly MailSummary[], grouped: boolean): MailLine[] {
  if (!grouped) return rows.map(row => ({ message: row, members: [row] }));
  const threads = new Map<string, MailSummary[]>();
  for (const row of rows) {
    const members = threads.get(row.thread_id);
    if (members) members.push(row);
    else threads.set(row.thread_id, [row]);
  }
  return [...threads.values()].map(conversationLine);
}

/** The messages a selection stands for: it ticks lines, an act takes messages. */
export function selectedMembers(
  lines: readonly MailLine[],
  selected: ReadonlySet<string>
): MailSummary[] {
  return lines.flatMap(line => (selected.has(line.message.id) ? line.members : []));
}

/** The ids a line stands for; an id no line shows stands for itself. */
export function lineMembers(lines: readonly MailLine[], id: string): string[] {
  const line = lines.find(item => item.message.id === id);
  return line ? line.members.map(member => member.id) : [id];
}

/**
 * Which message a conversation is read from: the reader's, unless it walks inside what was
 * read already, where nothing new would come of asking.
 *
 * @param anchor - The message it is read from now.
 * @param rows - What that read answered, once it did.
 * @param reading - The reader is open.
 * @param landedId - The message on screen, once it landed.
 */
export function conversationAnchor(
  anchor: string | null,
  rows: readonly MailSummary[] | undefined,
  reading: boolean,
  landedId: string | undefined
): string | null {
  if (!reading) return null;
  if (landedId === undefined) return anchor;
  return rows?.some(row => row.id === landedId) ? anchor : landedId;
}

/** Whether a listing is a place, which holds what it lists: where a move can come back to. */
export function isPlace(folder: string): boolean {
  return !folder.startsWith(SYSTEM_PREFIX) || PLACES.includes(folder);
}

/** What can be done to a message from where it is listed. */
export interface MailMoves {
  archive: boolean;
  spam: boolean;
  notSpam: boolean;
  restore: boolean;
  forever: boolean;
  move: boolean;
}

/**
 * Offers only what takes a message out of what is listed: a mailbox with no archive
 * folder (Gmail) archives by leaving the inbox, so a message of a label may not be there.
 *
 * @param folder - The listing.
 * @param folders - The pane; undefined until read.
 * @param permanentDelete - The provider can delete for good.
 */
export function movesFrom(
  folder: string,
  folders: readonly Pick<MailFolder, 'role'>[] | undefined,
  permanentDelete: boolean
): MailMoves {
  const own = !folder.startsWith(SYSTEM_PREFIX);
  const hasArchive = folders?.some(item => item.role === 'archive') ?? false;
  return {
    archive: folder === MAIL_INBOX || (own && hasArchive),
    spam: folder === MAIL_INBOX || own,
    notSpam: folder === MAIL_SPAM,
    restore: folder === MAIL_TRASH,
    forever: folder === MAIL_TRASH && permanentDelete,
    move: folder !== MAIL_SPAM && folder !== MAIL_TRASH,
  };
}

/** The ways a message is sent somewhere, each told in its own words. */
export type MailSendAct = 'trash' | 'archive' | 'spam' | 'not_spam' | 'restore' | 'move';

/** Where each act sends a message; `move` names its folder. */
export const SEND_PLACES: Readonly<Record<Exclude<MailSendAct, 'move'>, string>> = {
  trash: MAIL_TRASH,
  archive: MAIL_ARCHIVE,
  spam: MAIL_SPAM,
  not_spam: MAIL_INBOX,
  restore: MAIL_INBOX,
};

/** The act a drop on a folder is: the pane's places say more than « moved ». */
export function actOfDrop(folder: string): MailSendAct {
  if (folder === MAIL_TRASH) return 'trash';
  if (folder === MAIL_ARCHIVE) return 'archive';
  if (folder === MAIL_SPAM) return 'spam';
  return 'move';
}

/** Whether a folder takes a message dropped on it, from what is listed. */
export function takesDrop(folder: MailFolder, listed: string): boolean {
  return folder.id !== listed && (folder.kind === 'user' || isPlace(folder.id));
}

/** The messages a drag carries: the selection when it starts on it, else the row alone. */
export function draggedIds(id: string, selected: ReadonlySet<string>): string[] {
  return selected.has(id) ? [...selected] : [id];
}
