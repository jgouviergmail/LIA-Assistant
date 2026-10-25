/**
 * The relationship timeline, shaped for the page (owner request 2026-10-24).
 *
 * The API serves the card's own records merged by date, a page at a time
 * (`/relations/{name}/timeline`). The provider half — e-mails and meetings —
 * stays on the card's own windows (`/relations/{name}/context`), so it is merged
 * HERE, and only inside what the base pages already cover: a provider item
 * older than the oldest record loaded would jump ahead of records not yet
 * served. Once the base is exhausted, every provider item belongs.
 */

import type {
  ExchangedEmail,
  RelationCall,
  RelationContext,
  RelationMemory,
  RelationOpenLoop,
  RelationPeerMessage,
  SharedEvent,
} from '@/hooks/useRelations';
import type { SmsMessage } from '@/types/sms';

export type TimelineKind = 'call' | 'memory' | 'open_loop' | 'peer_message' | 'sms';

export interface RelationTimelineItem {
  kind: TimelineKind;
  at: string;
  open_loop?: RelationOpenLoop | null;
  call?: RelationCall | null;
  memory?: RelationMemory | null;
  peer_message?: RelationPeerMessage | null;
  sms?: SmsMessage | null;
}

/** No count of its own: the card's sections state theirs (ADR-185). */
export interface RelationTimelinePage {
  items: RelationTimelineItem[];
  next_cursor: string | null;
  page_size: number;
}

export type TimelineEntryKind = TimelineKind | 'email' | 'event';

/** One row of the section, whatever its source. */
export interface TimelineEntry {
  key: string;
  kind: TimelineEntryKind;
  at: string;
  /** The row's words; null when the record kept none (a relayed message past retention). */
  text: string | null;
  /** A second, quieter line (a call's summary, a mail's excerpt). */
  detail: string | null;
}

interface Projection {
  /** The record the kind names — its id keys the row. */
  id: string | undefined;
  text: string | null;
  detail: string | null;
}

/** How each kind reads, keyed by kind: a new kind cannot ship without its wording. */
const PROJECTIONS: { [K in TimelineKind]: (item: RelationTimelineItem) => Projection } = {
  open_loop: ({ open_loop }) => ({
    id: open_loop?.id,
    text: open_loop?.subject ?? null,
    detail: null,
  }),
  call: ({ call }) => ({
    id: call?.id,
    text: call?.objective ?? null,
    detail: call?.summary ?? null,
  }),
  memory: ({ memory }) => ({ id: memory?.id, text: memory?.content ?? null, detail: null }),
  peer_message: ({ peer_message }) => ({
    id: peer_message?.id,
    text: peer_message?.content ?? null,
    detail: null,
  }),
  sms: ({ sms }) => ({ id: sms?.id, text: sms?.body ?? null, detail: null }),
};

/** A record of the card, as its section words it. */
export function entryOf(item: RelationTimelineItem): TimelineEntry {
  const { id, text, detail } = PROJECTIONS[item.kind](item);
  return { key: `${item.kind}:${id ?? item.at}`, kind: item.kind, at: item.at, text, detail };
}

function emailEntry(email: ExchangedEmail): TimelineEntry | null {
  if (!email.occurred_at) return null;
  return {
    key: `email:${email.id}`,
    kind: 'email',
    at: email.occurred_at,
    text: email.subject,
    detail: email.excerpt,
  };
}

function eventEntry(event: SharedEvent): TimelineEntry | null {
  if (!event.starts_at) return null;
  return {
    key: `event:${event.id}`,
    kind: 'event',
    at: event.starts_at,
    text: event.summary,
    detail: null,
  };
}

/** The provider half: what already happened, and the meetings still to come. */
export interface ProviderEntries {
  past: TimelineEntry[];
  upcoming: TimelineEntry[];
}

export function providerEntries(context: RelationContext | null): ProviderEntries {
  const emails = (context?.emails.emails ?? []).map(emailEntry);
  const events = context?.events.events ?? [];
  const past = [...emails, ...events.filter(e => e.is_past).map(eventEntry)];
  const upcoming = events
    .filter(e => !e.is_past)
    .map(eventEntry)
    .filter((entry): entry is TimelineEntry => entry !== null)
    .sort((a, b) => a.at.localeCompare(b.at));
  return { past: past.filter((entry): entry is TimelineEntry => entry !== null), upcoming };
}

function instant(entry: TimelineEntry): number {
  return new Date(entry.at).getTime();
}

/**
 * The base records with the provider items their pages already cover, newest first.
 *
 * @param base - The records served so far, newest first.
 * @param provider - The provider items that already happened.
 * @param exhausted - Whether the base has nothing left to serve.
 */
export function mergeEntries(
  base: readonly TimelineEntry[],
  provider: readonly TimelineEntry[],
  exhausted: boolean
): TimelineEntry[] {
  // A fold, not `Math.min(...spread)`: the base grows with every page read.
  const oldest = base.reduce(
    (min, entry) => Math.min(min, instant(entry)),
    Number.POSITIVE_INFINITY
  );
  const covered = provider.filter(entry => exhausted || instant(entry) >= oldest);
  return [...base, ...covered].sort((a, b) => instant(b) - instant(a));
}

export interface TimelineDay {
  key: string;
  label: string;
  dayNumber: string;
  month: string;
  entries: TimelineEntry[];
}

/** Contiguous civil days of the reader's zone, in the entries' order. */
export function groupByDay(
  entries: readonly TimelineEntry[],
  lng: string,
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
): TimelineDay[] {
  const options = { timeZone };
  const dayKey = new Intl.DateTimeFormat('en-CA', {
    ...options,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  const label = new Intl.DateTimeFormat(lng, { ...options, dateStyle: 'full' });
  const dayNumber = new Intl.DateTimeFormat(lng, { ...options, day: 'numeric' });
  const month = new Intl.DateTimeFormat(lng, { ...options, month: 'short' });
  const days: TimelineDay[] = [];
  for (const entry of entries) {
    const date = new Date(entry.at);
    if (!Number.isFinite(date.getTime())) continue;
    const key = dayKey.format(date);
    let day = days.at(-1);
    if (!day || day.key !== key) {
      day = {
        key,
        label: label.format(date),
        dayNumber: dayNumber.format(date),
        month: month.format(date),
        entries: [],
      };
      days.push(day);
    }
    day.entries.push(entry);
  }
  return days;
}
