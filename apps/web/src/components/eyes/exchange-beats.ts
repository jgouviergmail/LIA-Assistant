/**
 * The beats the EXCHANGE earns from the face while a turn is under way.
 *
 * A wait lasts half a minute at the median, and until 2026-11-12 the face
 * marked neither its beginning nor anything that happened in it. Two beats
 * now do, both on EVIDENCE and both from the vocabulary the rig already owns:
 *
 *  - a message was sent: the face acknowledges it (`perk` — attention is a
 *    brow raise before it is anything else);
 *  - a tool finished with something to show for it: a blink, as at any
 *    boundary of attention, and the brows lift (`brow-twitch` — something
 *    crossed the mind).
 *
 * The exchange ends on a third: the delivered answer is presented, in its
 * register's manner (`deliveryGesture`, `tone.ts`), and handed over a moment
 * later — « à toi » — unless the person has started writing meanwhile.
 *
 * Pure decisions; the host plays them (`useEyesBehavior`). A plan, a requested
 * call, a failed, cancelled, waiting or unknown end mark nothing: the face
 * never celebrates what the execution evidence does not say.
 */

import type { ActivityRecord } from './activity';
import {
  isPresentationGesture,
  type IdleGesture,
  type PresentationGesture,
} from './expression-engine';

/** What the face does when a message leaves. */
export const ACKNOWLEDGEMENT_GESTURE = 'perk' satisfies IdleGesture;

/** What the face does when a tool comes back with a result. */
export const TOOL_DONE_GESTURE = 'brow-twitch' satisfies IdleGesture;

/** A message was just sent: the status the face sees turned to `sending`. */
export function messageSent(previous: string, current: string): boolean {
  return current === 'sending' && previous !== 'sending';
}

/**
 * The identity of the last tool that finished with a result, or null.
 *
 * An identity, not a time: the delivered answer stamps the same evidence
 * again (`completeTurn`), and a recall is not another tool. The outcome is
 * the whole test: only a finished tool has one (`activity.ts`).
 */
export function finishedToolKey(record: ActivityRecord | null): string | null {
  if (!record) return null;
  const { outcome, run_id: run, invocation_id: invocation } = record.event;
  if (outcome !== 'succeeded' && outcome !== 'prepared') return null;
  return `${run}:${invocation}`;
}

/**
 * What the face does once a presented answer has been seen: « à toi » — it
 * leans in a little and waits for the person (`rig/delivery.ts`).
 */
export const HAND_OVER_GESTURE = 'listen' satisfies IdleGesture;

/**
 * When, after the presentation starts, the face hands the answer over: once
 * the look, the open hand and the register's « voilà » have been seen, and
 * while the answer still holds the face (`REACTION_HOLD_MS`).
 */
export const HAND_OVER_AFTER_MS = 3000;

/** Whether a delivery beat is a presentation, which a hand-over follows. A
 * declared accent is the model's own punctuation and ends the delivery. */
export function handsOver(delivery: IdleGesture | null): delivery is PresentationGesture {
  return isPresentationGesture(delivery);
}

/**
 * Whether the hand-over is still owed when its time comes: the answer the
 * face presented is still the one it holds (no other answer, no new turn,
 * which clears it), and the person has not started writing — the face then
 * follows the text (`isAttending`, ADR-294).
 */
export function mayHandOver(
  heldAnswerAt: number | null,
  presentedAt: number,
  attending: boolean
): boolean {
  return heldAnswerAt === presentedAt && !attending;
}
