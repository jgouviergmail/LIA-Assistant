/**
 * What a ticket LOOKS like, decided once (ADR-276).
 *
 * Pure functions, no React: a card, a hub row and a detail panel all answer the
 * same four questions — who holds it, is it late, how far along are its steps,
 * what did its last run do — and three components answering them separately is
 * how the same ticket comes to read differently on two screens.
 */
import type { EventRow, TicketRow } from '@/types/workboard';
import { CLOSED_STATUSES } from '@/types/workboard';

/** A connected peer, reduced to what a name lookup needs. */
export interface PeerName {
  peer_id: string;
  peer_display_name: string;
}

/** Who a ticket names, once the ids have been resolved to people. */
export type PartyLabel =
  | { kind: 'lia' }
  | { kind: 'me' }
  | { kind: 'peer'; name: string }
  | { kind: 'unknown' };

/**
 * Who holds this ticket.
 *
 * The board payload carries ids, never names: a peer's name comes from the
 * accepted connections this account already fetched. A connection removed since
 * the ticket was assigned resolves to `unknown` rather than to a blank — the
 * reader must see that someone else holds it, even unnamed.
 *
 * @param ticket - The row.
 * @param meId - The reading account.
 * @param peers - Accepted connections.
 * @returns Which party holds it, and their name when there is one.
 */
export function assigneeParty(
  ticket: Pick<TicketRow, 'assignee_kind' | 'effective_assignee_id'>,
  meId: string | undefined,
  peers: readonly PeerName[]
): PartyLabel {
  if (ticket.assignee_kind === 'lia') return { kind: 'lia' };
  return partyOf(ticket.effective_assignee_id, meId, peers);
}

/**
 * Who owns the board a ticket was created on.
 *
 * A ticket a peer handed over shows on this account's board with the OTHER
 * person as its owner; naming them is what tells « my work » from « theirs ».
 *
 * @param ticket - The row.
 * @param meId - The reading account.
 * @param peers - Accepted connections.
 * @returns Which party owns it.
 */
export function ownerParty(
  ticket: Pick<TicketRow, 'owner_user_id'>,
  meId: string | undefined,
  peers: readonly PeerName[]
): PartyLabel {
  return partyOf(ticket.owner_user_id, meId, peers);
}

function partyOf(userId: string, meId: string | undefined, peers: readonly PeerName[]): PartyLabel {
  if (meId && userId === meId) return { kind: 'me' };
  const peer = peers.find(connection => connection.peer_id === userId);
  return peer ? { kind: 'peer', name: peer.peer_display_name } : { kind: 'unknown' };
}

/** Whether a column means the work is over. */
export function isClosed(status: string): boolean {
  return (CLOSED_STATUSES as readonly string[]).includes(status);
}

/**
 * Whether a ticket is past its due date and still open.
 *
 * A closed ticket is never late: it is finished, and painting « en retard » on
 * something the person completed last month is a reproach, not a fact.
 *
 * @param ticket - The row.
 * @param now - The instant to compare against (injected, so the test owns time).
 * @returns True when it is overdue.
 */
export function isOverdue(
  ticket: Pick<TicketRow, 'due_at' | 'status'>,
  now: Date = new Date()
): boolean {
  if (!ticket.due_at || isClosed(ticket.status)) return false;
  const due = new Date(ticket.due_at).getTime();
  return Number.isFinite(due) && due < now.getTime();
}

/**
 * How far a ticket's steps have got — or nothing, when nobody can be sure.
 *
 * A count shown to the reader is EXACT or it does not exist (ADR-185). The
 * children are ordinary rows, so they are only all in hand when the page holds
 * the whole board; past that, the panel's own read is the authority and the
 * card says nothing rather than under-reporting.
 *
 * @param ticket - The parent.
 * @param loaded - Every row the board currently holds.
 * @param total - The EXACT number of rows the filter matches.
 * @returns `{done, total}`, or null when the page is not the whole board.
 */
export function childProgress(
  ticket: Pick<TicketRow, 'id'>,
  loaded: readonly TicketRow[],
  total: number
): { done: number; total: number } | null {
  if (loaded.length < total) return null;
  const children = loaded.filter(row => row.parent_id === ticket.id);
  if (children.length === 0) return null;
  return { done: children.filter(row => isClosed(row.status)).length, total: children.length };
}

/** What the last run of a ticket leaves on its card. */
export type RunState = 'running' | 'waiting' | 'failed' | 'succeeded' | null;

/**
 * What LIA's last run did, as the card states it.
 *
 * The COLUMN is read first: a ticket LIA is running right now is `in_progress`
 * with a claim, and the previous run's outcome must not describe it. A refusal
 * for quota or for a busy conversation is deliberately NOT a failure — it is a
 * run that did not happen, and the card says nothing rather than accusing.
 *
 * @param ticket - The row.
 * @returns The state to show, or null when there is nothing to say.
 */
export function runState(
  ticket: Pick<TicketRow, 'status' | 'assignee_kind' | 'last_run_outcome' | 'run_claimed_at'>
): RunState {
  if (ticket.assignee_kind !== 'lia') return null;
  // « Running » is the CLAIM, never the column. A failed run leaves the ticket
  // in the `in_progress` it was found in, so reading the status said « LIA y
  // travaille » for good on a ticket where nothing was going to happen, and
  // hid the error line, which only renders on `failed`. Reading the outcome
  // first would have been the opposite mistake: a run in flight still carries
  // the PREVIOUS run's outcome. The claim is the one thing that means « now ».
  if (ticket.run_claimed_at) return 'running';
  if (ticket.status === 'waiting') return 'waiting';
  if (ticket.last_run_outcome === 'failed') return 'failed';
  if (ticket.last_run_outcome === 'success') return 'succeeded';
  return null;
}

/**
 * Which wording the history shows for an event.
 *
 * The log stores one kind per fact, and « assigned » covers three facts a
 * reader must not confuse: a ticket handed to somebody, a ticket a holder
 * handed BACK, and a ticket that came back on its own because the connection
 * ended (ADR-276 lot 5). The first is progress, the other two are the ticket
 * returning to the owner — showing « Handed over » on a ticket that was just
 * handed back reads as the opposite of what happened.
 *
 * A column change that is the person's ANSWER to a confirmation (lot 7) is
 * named by the answer: « Action approuvée » says why the ticket moved, where
 * « Colonne changée » would hide that their word moved it. The hand-over to
 * LIA that follows keeps its own wording — it is the same hand-over as ever.
 *
 * Reads the payload the service writes; an event with no payload keeps the
 * kind's own wording.
 */
export function eventLabelKey(event: Pick<EventRow, 'kind' | 'payload'>): string {
  if (event.kind === 'status_changed' && event.payload) {
    if (event.payload.reason === 'approve') return 'workboard.events.approved';
    if (event.payload.reason === 'amend') return 'workboard.events.amended';
    if (event.payload.reason === 'refuse') return 'workboard.events.refused';
  }
  if (event.kind === 'assigned' && event.payload) {
    if (event.payload.reason === 'connection_removed') return 'workboard.events.released';
    // A run that stopped on a question, or delivered a result to validate,
    // gave the ticket back — « Confié » would say the opposite, and a bare
    // « Rendu » said nothing (owner, 2026-09-09): it names LIA and the reader.
    if (event.payload.reason === 'handed_back') return 'workboard.events.returned_by_run';
    if (event.payload.from_user && !event.payload.to_user && event.payload.to_kind === 'human') {
      return 'workboard.events.returned';
    }
  }
  return `workboard.events.${event.kind}`;
}

/**
 * Which option of the « who holds it » control is the current one.
 *
 * `null` means « the owner holds it » (ADR-276) and the owner's own id means
 * the same thing, so both spellings of that one fact resolve to `me`. Anything
 * else is a connected peer, named by their id.
 */
export function heldBy(
  ticket: Pick<TicketRow, 'assignee_kind' | 'assignee_user_id' | 'owner_user_id'>
): string {
  if (ticket.assignee_kind === 'lia') return 'lia';
  const holder = ticket.assignee_user_id ?? ticket.owner_user_id;
  return holder === ticket.owner_user_id ? 'me' : holder;
}

/**
 * The patch that hands a ticket to the chosen party.
 *
 * `me` and `lia` are KEYWORDS the service resolves; anything else is a peer's
 * id, and the two travel in different fields — sending a peer id as the
 * keyword would be refused, and sending `me` as an id would name nobody.
 */
export function assignPatch(choice: string): {
  assignee?: 'me' | 'lia';
  assignee_user_id?: string | null;
} {
  return choice === 'me' || choice === 'lia' ? { assignee: choice } : { assignee_user_id: choice };
}

/** One change a history entry records, as values rather than as a sentence. */
export type EventChange =
  | { field: 'status' | 'priority'; from: string | null; to: string | null }
  | { field: 'start' | 'due'; from: string | null; to: string | null }
  | { field: 'created_in'; to: string | null }
  | { field: 'follow'; on: boolean };

/**
 * What an entry actually changed, before → after.
 *
 * « Priorité modifiée » says a fact nobody can act on; « Priorité : moyenne →
 * urgente » says what happened. The values come back RAW — a status key, a
 * priority key, an ISO instant — because translating and formatting them is
 * the reader's business, not the log's: the same entry reads in six languages
 * and in the reader's own timezone.
 *
 * A date change carries two fields at once and yields one entry per field that
 * actually moved: setting only the due date must not claim the start date
 * changed too.
 */
export function eventChanges(event: Pick<EventRow, 'kind' | 'payload'>): EventChange[] {
  const payload = event.payload;
  if (!payload) return [];
  const text = (key: string): string | null => {
    const value = payload[key];
    return typeof value === 'string' && value ? value : null;
  };

  switch (event.kind) {
    case 'created':
      // One value, not two: nothing preceded it, and « aucune → À faire »
      // would invent a state the ticket never had.
      return [{ field: 'created_in', to: text('status') }];
    case 'status_changed':
      return [{ field: 'status', from: text('from'), to: text('to') }];
    case 'priority_changed':
      return [{ field: 'priority', from: text('from'), to: text('to') }];
    case 'follow_changed':
      return typeof payload.to === 'boolean' ? [{ field: 'follow', on: payload.to }] : [];
    case 'dates_changed': {
      const moved: EventChange[] = [];
      for (const [field, before, after] of [
        ['start', 'from_start', 'to_start'],
        ['due', 'from_due', 'to_due'],
      ] as const) {
        const from = text(before);
        const to = text(after);
        if (from !== to) moved.push({ field, from, to });
      }
      return moved;
    }
    default:
      return [];
  }
}
