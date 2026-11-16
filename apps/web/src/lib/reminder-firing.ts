/**
 * A fired reminder's postponement, as the web knows it (ADR-268 amendment 2026-11-16).
 *
 * The server records every occurrence that rings; the chat bubble, the toast and
 * the world's device name it by `firing_id` and press the same three « later »
 * and « stop ». This module holds what they share:
 *
 * - the wire shapes of `/reminders/firings/{id}`;
 * - the bubble's gate (`reminderFiringOf`), read from the archived metadata;
 * - the delay label, said in whole hours when it is one (as the push and
 *   Telegram say it, from the server's table);
 * - ONE memory of the verdicts given on this page, so a press on the toast
 *   settles the bubble of the same occurrence without a reread.
 */

import { useSyncExternalStore } from 'react';

/** The bubble's metadata type for a reminder that rang (backend constant). */
export const REMINDER_NOTIFICATION_TYPE = 'reminder_notification';

/** What `GET /reminders/firings/{id}` answers. */
export interface ReminderFiringState {
  id: string;
  fired_at: string;
  snoozable_until: string;
  snoozed_until: string | null;
  stoppable: boolean;
  short_minutes: number;
  long_minutes: number;
}

/** The three « later ». */
export type SnoozeChoice = 'short' | 'long' | 'morning';

/** Where a press came from (the server counts it). */
export type SnoozeSurface = 'chat' | 'push';

/** What a snooze press did. */
export interface SnoozeVerdict {
  outcome: 'snoozed' | 'already_snoozed' | 'expired' | 'collides';
  snoozed_until: string | null;
  next_occurrence_at: string | null;
}

/** What a « stop this reminder » press did. */
export interface StopVerdict {
  outcome: 'stopped' | 'already_stopped';
}

/** What a reminder event offers to postpone: its occurrence and the short delay. */
export interface ReminderSnoozeOffer {
  firingId: string;
  shortMinutes: number;
}

/** The endpoints of one occurrence. */
export const firingEndpoint = (firingId: string): string => `/reminders/firings/${firingId}`;

/**
 * The occurrence a bubble names, while its window is open.
 *
 * Read once per render: past `snoozable_until` the bubble offers nothing and
 * asks the server nothing — an old reminder in the history costs no request.
 *
 * @param metadata - The bubble's metadata, possibly absent.
 * @param now - The present, in milliseconds.
 * @returns The occurrence's id, or null.
 */
export function reminderFiringOf(
  metadata: Record<string, unknown> | undefined,
  now: number
): string | null {
  if (!metadata || metadata.type !== REMINDER_NOTIFICATION_TYPE) return null;
  const firingId = metadata.firing_id;
  const until = metadata.snoozable_until;
  if (typeof firingId !== 'string' || firingId.length === 0 || typeof until !== 'string') {
    return null;
  }
  const closesAt = Date.parse(until);
  return Number.isFinite(closesAt) && closesAt > now ? firingId : null;
}

/**
 * A delay as a button says it: whole hours in hours, the rest in minutes.
 *
 * @param minutes - The delay.
 * @returns The translation key and its count.
 */
export function delayLabelKey(minutes: number): { key: string; count: number } {
  return minutes % 60 === 0
    ? { key: 'reminders.firing.in_hours', count: minutes / 60 }
    : { key: 'reminders.firing.in_minutes', count: minutes };
}

/** What this page learned of an occurrence since its state was read. */
export interface FiringVerdict {
  snoozedUntil?: string;
  expired?: boolean;
  stopped?: boolean;
}

/** Verdicts kept per page: a person presses a handful; the oldest go first. */
const VERDICTS_KEPT = 64;
const verdicts = new Map<string, FiringVerdict>();
const listeners = new Set<() => void>();

/**
 * Remember what a press did, for every surface showing the same occurrence.
 *
 * @param firingId - The occurrence.
 * @param verdict - What changed.
 */
export function recordFiringVerdict(firingId: string, verdict: FiringVerdict): void {
  const merged = { ...verdicts.get(firingId), ...verdict };
  verdicts.delete(firingId);
  verdicts.set(firingId, merged);
  while (verdicts.size > VERDICTS_KEPT) {
    const oldest = verdicts.keys().next();
    if (oldest.done) break;
    verdicts.delete(oldest.value);
  }
  for (const listener of listeners) listener();
}

/**
 * The verdict a snooze answer carries, for `recordFiringVerdict`.
 *
 * @param verdict - The server's answer.
 * @returns What the surfaces must now show, or null when nothing settled.
 */
export function snoozeVerdictOf(verdict: SnoozeVerdict): FiringVerdict | null {
  if (verdict.outcome === 'expired') return { expired: true };
  if (verdict.snoozed_until) return { snoozedUntil: verdict.snoozed_until };
  return null;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * The verdict this page holds for an occurrence.
 *
 * @param firingId - The occurrence, or null.
 * @returns Its verdict, or undefined.
 */
export function useFiringVerdict(firingId: string | null): FiringVerdict | undefined {
  return useSyncExternalStore(
    subscribe,
    () => (firingId ? verdicts.get(firingId) : undefined),
    () => undefined
  );
}

/** Forget every verdict (tests). */
export function resetFiringVerdicts(): void {
  verdicts.clear();
  for (const listener of listeners) listener();
}
