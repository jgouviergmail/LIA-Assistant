/**
 * What one tool hands to another (ADR-369, lots 2 and 6): a message becoming a task,
 * a contact to write to, a file leaving by mail.
 *
 * It is held in the page, for the next tool that opens, and taken once: a subject
 * or an address has no place in a URL every server on the way would log. A reload
 * loses it, as it would lose a form.
 */

import type { ProposedEvent } from './assist';
import type { MemoryCreate } from '@/hooks/useMemories';
import type { ProposedReminder, ProposedTicket } from '@/lib/selection-assist/contracts';
import { APPLICATION_HANDOFF_TTL_MS } from '@/lib/constants';
import { generateUUID } from '@/lib/utils';
import type { AttachableFile, WorkbenchToolId } from './types';

/** Each thing a tool can be handed, named by what it starts. */
export type WorkbenchHandoff =
  /**
   * `due`, `list_name`, `importance`: what LIA read for it, which the person keeps or not in the
   * form it opens.
   */
  | {
      kind: 'task';
      title: string;
      notes: string;
      due?: string | null;
      list_name?: string | null;
      importance?: 'high' | null;
    }
  /** `proposal`: what LIA read of it, for the editor to open on. */
  | { kind: 'event'; summary: string; description: string; proposal?: ProposedEvent }
  /** `phone`: a number to save, the home's SMS sender (2026-11-07). */
  | { kind: 'contact'; name: string; email: string; phone?: string }
  /** `assisted`: the message is to be written with LIA, from the person's instruction. */
  | {
      kind: 'compose';
      to: string;
      subject?: string;
      file?: AttachableFile;
      assisted?: boolean;
    };

export type HandoffKind = WorkbenchHandoff['kind'];
export type ApplicationHandoff =
  | WorkbenchHandoff
  | { kind: 'memory'; memory: MemoryCreate }
  | { kind: 'reminder'; reminder: ProposedReminder }
  | { kind: 'ticket'; ticket: ProposedTicket };
export type ApplicationHandoffKind = ApplicationHandoff['kind'];

/** The tool each thing opens in. */
export const HANDOFF_TOOLS: Readonly<Record<HandoffKind, WorkbenchToolId>> = {
  task: 'tasks',
  event: 'calendar',
  contact: 'contacts',
  compose: 'mail',
};

export interface PendingHandoff {
  readonly id: string;
  readonly owner: string;
  readonly expiresAt: number;
  readonly payload: ApplicationHandoff;
}
let owner: string | null = null;
let waiting: PendingHandoff | null = null;
let expiry: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();
const publish = () => listeners.forEach(listener => listener());
function clear(): void {
  clearTimeout(expiry);
  expiry = undefined;
  waiting = null;
  publish();
}
/** Auth owns the lifetime; navigation never resets it. Logout also releases all payload text. */
export function setHandoffOwner(next: string | null): void {
  if (owner === next) return;
  owner = next;
  clear();
}
export const handoffStore = {
  getSnapshot: (): PendingHandoff | null => waiting,
  getServerSnapshot: (): null => null,
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};

/** Leaves it for the tool that opens next; the last thing handed wins. */
export function handOff(account: string, handoff: ApplicationHandoff): boolean {
  if (!account || account !== owner) return false;
  clearTimeout(expiry);
  waiting = {
    id: generateUUID(),
    owner: account,
    expiresAt: Date.now() + APPLICATION_HANDOFF_TTL_MS,
    payload: structuredClone(handoff),
  };
  expiry = setTimeout(clear, APPLICATION_HANDOFF_TTL_MS);
  publish();
  return true;
}

function hasKind<K extends ApplicationHandoffKind>(
  value: ApplicationHandoff,
  kind: K
): value is Extract<ApplicationHandoff, { kind: K }> {
  return value.kind === kind;
}

/**
 * @param kind - What the tool takes.
 * @returns What was handed to it, once; null for anything else.
 */
export function takeHandoff<K extends ApplicationHandoffKind>(
  kind: K,
  account: string,
  expectedId?: string
): Extract<ApplicationHandoff, { kind: K }> | null {
  const held = waiting;
  if (!held || held.owner !== account || account !== owner) return null;
  if (held.expiresAt <= Date.now()) {
    clear();
    return null;
  }
  if (expectedId !== undefined && held.id !== expectedId) return null;
  if (!hasKind(held.payload, kind)) return null;
  clear();
  return held.payload;
}
