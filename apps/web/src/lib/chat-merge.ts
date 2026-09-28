/**
 * Merging the newest server page into the thread on screen (ADR-320).
 *
 * The chat used to REPLACE its whole list whenever it re-read the server: every
 * bubble remounted (a flash, a lost selection, a collapsed disclosure), the
 * older pages the reader had scrolled into vanished, and the live bubbles of a
 * turn were swapped for their archived rows. A merge keeps what is already on
 * screen and adds what is not:
 *
 * - **A bubble is recognised by the ids it may carry** — its own id (a history
 *   row, a live-session row) or the `message_db_id` a live bubble learns from
 *   its `done` chunk. A bubble that learned neither (an interrupted turn, a
 *   HITL question archived after its stream ended) is paired by role and text,
 *   but only among bubbles nothing else claimed, and never an archived row
 *   against another: two rows with the same words are two rows.
 * - **What did not change keeps its identity** — the same object, so React
 *   re-renders nothing and the reader's selection, focus and open panels stay.
 *   A history row the server changed since (a rewritten card, a restated file,
 *   a late token count) is taken from the server under the SAME id: a
 *   re-render, never a remount. A live bubble keeps what its stream gave it.
 * - **What exists only here stays where it was** — an error bubble, a question
 *   still in flight: each follows the bubble it followed.
 * - **An empty page never empties the thread**: a failed read and an emptied
 *   conversation look alike, and a reset is announced by its own signal.
 * - **More than a page arrived while away** (nothing on screen is in the page,
 *   and the page is newer than everything on screen): the page replaces the
 *   thread and the caller restarts its scroll-up pagination from it — the one
 *   case where a merge cannot know what lies between the two.
 */

import type { Message } from '@/types/chat';

/** The result of merging one server page. */
export interface ServerPageMerge {
  /** The thread after the merge — the SAME array when nothing changed. */
  messages: Message[];
  /** The page does not reach back to the thread on screen: `messages` is the
   *  page (plus the bubbles that exist only here) and older history must be
   *  paginated again from it. */
  gap: boolean;
}

interface Pairing {
  /** Local index → server index. */
  localToServer: Map<number, number>;
  /** Server index → local index. */
  serverToLocal: Map<number, number>;
  /** Local bubbles that repeat a server row another bubble already claimed. */
  duplicates: Set<number>;
  /** First local index paired BY ID, or -1. */
  firstIdMatch: number;
}

/** The ids a bubble may be known by on the server. */
function serverIdsOf(message: Message): string[] {
  const dbId = message.metadata?.message_db_id;
  return typeof dbId === 'string' && dbId !== message.id ? [message.id, dbId] : [message.id];
}

/** A bubble the history read produced (it names its archived row). */
function isArchivedRow(message: Message): boolean {
  return typeof message.metadata?.message_db_id === 'string';
}

function normalizedText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/** What a history row shows: two rows with equal fingerprints render the same. */
function fingerprint(message: Message): string {
  return JSON.stringify([
    message.content,
    message.metadata ?? null,
    message.tokensIn ?? null,
    message.tokensOut ?? null,
    message.tokensCache ?? null,
    message.costEur ?? null,
    message.googleApiRequests ?? null,
    message.ttsCostEur ?? null,
    message.sttCostEur ?? null,
  ]);
}

function pairById(local: Message[], server: Message[]): Pairing {
  const serverIndex = new Map(server.map((message, index) => [message.id, index]));
  const pairing: Pairing = {
    localToServer: new Map(),
    serverToLocal: new Map(),
    duplicates: new Set(),
    firstIdMatch: -1,
  };
  local.forEach((message, localIndex) => {
    const serverId = serverIdsOf(message).find(id => serverIndex.has(id));
    if (serverId === undefined) return;
    const index = serverIndex.get(serverId) as number;
    if (pairing.serverToLocal.has(index)) {
      pairing.duplicates.add(localIndex);
      return;
    }
    pairing.localToServer.set(localIndex, index);
    pairing.serverToLocal.set(index, localIndex);
    if (pairing.firstIdMatch < 0) pairing.firstIdMatch = localIndex;
  });
  return pairing;
}

/** Pair the bubbles no id names with unclaimed rows of the same role and text. */
function pairByContent(local: Message[], server: Message[], pairing: Pairing, from: number): void {
  for (let localIndex = from; localIndex < local.length; localIndex += 1) {
    const message = local[localIndex];
    const pairable =
      !pairing.localToServer.has(localIndex) &&
      !pairing.duplicates.has(localIndex) &&
      !isArchivedRow(message) &&
      message.metadata?.type !== 'error';
    if (!pairable) continue;
    const text = normalizedText(message.content);
    const index = server.findIndex(
      (row, serverIndex) =>
        !pairing.serverToLocal.has(serverIndex) &&
        row.role === message.role &&
        normalizedText(row.content) === text
    );
    if (index < 0) continue;
    pairing.localToServer.set(localIndex, index);
    pairing.serverToLocal.set(index, localIndex);
  }
}

/** Where the part of the thread the page speaks about starts. */
function windowStart(local: Message[], pairing: Pairing): number {
  if (pairing.firstIdMatch >= 0) return pairing.firstIdMatch;
  // Nothing on screen is in the page: what follows the newest archived row is
  // live (a turn, an error) and belongs to the page's end.
  for (let index = local.length - 1; index >= 0; index -= 1) {
    if (isArchivedRow(local[index])) return index + 1;
  }
  return 0;
}

function newestArchivedTime(local: Message[]): number | null {
  for (let index = local.length - 1; index >= 0; index -= 1) {
    if (isArchivedRow(local[index])) return local[index].timestamp.getTime();
  }
  return null;
}

/** The server row a bubble became, adopted without losing what the bubble holds. */
function adopt(localMessage: Message, serverMessage: Message): Message {
  if (localMessage.id === serverMessage.id) {
    return fingerprint(localMessage) === fingerprint(serverMessage) ? localMessage : serverMessage;
  }
  if (localMessage.metadata?.message_db_id === serverMessage.id) return localMessage;
  return {
    ...localMessage,
    metadata: { ...localMessage.metadata, message_db_id: serverMessage.id },
  };
}

/** The page in server order, each row as the bubble already on screen when there is one,
 *  and every bubble that exists only here after the bubble it followed. */
function buildWindow(
  local: Message[],
  server: Message[],
  pairing: Pairing,
  start: number
): Message[] {
  const after = new Map<number, Message[]>();
  const unanchored: Message[] = [];
  let anchor = -1;
  for (let index = start; index < local.length; index += 1) {
    const serverIndex = pairing.localToServer.get(index);
    if (serverIndex !== undefined) {
      anchor = serverIndex;
    } else if (!pairing.duplicates.has(index)) {
      const bucket = anchor < 0 ? unanchored : (after.get(anchor) ?? []);
      bucket.push(local[index]);
      if (anchor >= 0) after.set(anchor, bucket);
    }
  }
  const window: Message[] = [];
  server.forEach((row, serverIndex) => {
    const localIndex = pairing.serverToLocal.get(serverIndex);
    window.push(localIndex === undefined ? row : adopt(local[localIndex], row));
    window.push(...(after.get(serverIndex) ?? []));
  });
  // Bubbles nothing anchors are live ones, newer than the page.
  return [...window, ...unanchored];
}

function sameThread(a: Message[], b: Message[]): boolean {
  return a.length === b.length && a.every((message, index) => message === b[index]);
}

/**
 * Merge the newest server page into the thread on screen.
 *
 * @param local - The thread on screen, oldest first.
 * @param server - The newest page the server serves, oldest first.
 * @returns The merged thread (the same array when nothing changed) and whether
 *   the page lay beyond everything on screen.
 */
export function mergeServerPage(local: Message[], server: Message[]): ServerPageMerge {
  if (server.length === 0) return { messages: local, gap: false };
  const pairing = pairById(local, server);
  const newest = newestArchivedTime(local);
  if (pairing.firstIdMatch < 0 && newest !== null) {
    const pageOldest = server[0].timestamp.getTime();
    if (pageOldest <= newest) {
      // A page older than what is on screen: a stale read, nothing to add.
      return { messages: local, gap: false };
    }
    const start = windowStart(local, pairing);
    pairByContent(local, server, pairing, start);
    return { messages: buildWindow(local, server, pairing, start), gap: true };
  }
  const start = windowStart(local, pairing);
  pairByContent(local, server, pairing, start);
  const merged = [...local.slice(0, start), ...buildWindow(local, server, pairing, start)];
  return { messages: sameThread(merged, local) ? local : merged, gap: false };
}
