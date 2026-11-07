/**
 * What one tool hands to another (ADR-369, lots 2 and 6): a message becoming a task,
 * a contact to write to, a file leaving by mail.
 *
 * It is held in the page, for the next tool that opens, and taken once: a subject
 * or an address has no place in a URL every server on the way would log. A reload
 * loses it, as it would lose a form.
 */

import type { ProposedEvent } from './assist';
import type { AttachableFile } from './types';

/** Each thing a tool can be handed, named by what it starts. */
export type WorkbenchHandoff =
  /** `due`: the day LIA read for it, which the person keeps or not. */
  | { kind: 'task'; title: string; notes: string; due?: string | null }
  /** `proposal`: what LIA read of it, for the editor to open on. */
  | { kind: 'event'; summary: string; description: string; proposal?: ProposedEvent }
  | { kind: 'contact'; name: string; email: string }
  | { kind: 'compose'; to: string; file?: AttachableFile };

export type HandoffKind = WorkbenchHandoff['kind'];

let waiting: WorkbenchHandoff | null = null;

/** Leaves it for the tool that opens next; the last thing handed wins. */
export function handOff(handoff: WorkbenchHandoff): void {
  waiting = handoff;
}

/**
 * @param kind - What the tool takes.
 * @returns What was handed to it, once; null for anything else.
 */
export function takeHandoff<K extends HandoffKind>(
  kind: K
): Extract<WorkbenchHandoff, { kind: K }> | null {
  const held = waiting;
  if (held?.kind !== kind) return null;
  waiting = null;
  return held as Extract<WorkbenchHandoff, { kind: K }>;
}
