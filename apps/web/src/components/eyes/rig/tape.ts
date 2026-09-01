/**
 * Tapes — a short, timed sequence of targets for ONE channel.
 *
 * This is the single mechanism behind four things that used to be four
 * mechanisms (a CSS keyframe, a class the host toggled on a timer, a scripted
 * "performance", and nothing at all for anticipation):
 *
 *  - ANTICIPATION: a small counter-move before the real target. The rule an
 *    animator states first and the old system could not express at all — a
 *    CSS transition interpolates in a straight line between two poses.
 *  - the blink, as a real closure channel rather than a keyframe that fought
 *    whatever transform the pose wanted;
 *  - one-shot beats (an arrival pop, a tilt, a bounce);
 *  - multi-beat performances (the startled wake-up, the idle daydreams).
 *
 * A tape OWNS its channel's target while it plays, then hands it back to the
 * pose. It never writes the value itself: the spring still does all the
 * interpolation, so a tape can be interrupted at any moment without a jump.
 */

import type { ChannelKey } from '@/components/eyes/rig/channels';
import type { SpringConfig } from '@/components/eyes/rig/spring';

export interface TapeKey {
  /** Milliseconds from the start of the tape. */
  readonly atMs: number;
  readonly value: number;
}

export interface Tape {
  readonly channel: ChannelKey;
  /** Ordered by `atMs`; the first key is normally at 0. */
  readonly keys: readonly TapeKey[];
  /** How long the tape owns the channel. Defaults to the last key's time —
   * give it a longer value to HOLD the last key before releasing. */
  readonly durationMs?: number;
  /** Spring to use while this tape plays, overriding the expression's own.
   * A blink is fast whatever mood the face is in. */
  readonly spring?: SpringConfig;
  /** Keys are OFFSETS from the pose rather than absolute targets. A brow
   * raise means "a bit higher than wherever this eye currently sits" — an
   * absolute target would yank a squashed joy eye up to a neutral height. */
  readonly relative?: boolean;
}

/** How long the tape owns its channel. */
export function tapeDurationMs(tape: Tape): number {
  const lastKey = tape.keys.length > 0 ? tape.keys[tape.keys.length - 1].atMs : 0;
  return Math.max(tape.durationMs ?? 0, lastKey);
}

/**
 * The target this tape dictates at `elapsedMs`, or `null` once it is over
 * (the pose takes the channel back).
 *
 * Keys are STEPS, not interpolations: the spring between two keys is what
 * makes the motion, which is why a two-key tape produces a real anticipation
 * arc rather than a linear ramp.
 */
export function tapeTargetAt(tape: Tape, elapsedMs: number): number | null {
  if (elapsedMs < 0 || elapsedMs > tapeDurationMs(tape) || tape.keys.length === 0) return null;
  // A first key placed after 0 is a START DELAY: the tape has not taken the
  // channel yet. That is how the right eye trails the left one by 70-90 ms
  // without a second mechanism.
  if (elapsedMs < tape.keys[0].atMs) return null;
  let value = tape.keys[0].value;
  for (const key of tape.keys) {
    if (key.atMs > elapsedMs) break;
    value = key.value;
  }
  return value;
}

/**
 * Build the anticipation tape for a move from `from` to `to`.
 *
 * The eye pulls slightly AWAY from where it is about to go, then commits.
 * Returns `null` when the move is too small to be worth anticipating — below
 * that threshold the counter-move reads as a glitch, not as intent.
 */
export function anticipationTape(
  channel: ChannelKey,
  from: number,
  to: number,
  options: { ratio: number; leadMs: number; minDelta: number; maxOffset?: number }
): Tape | null {
  const delta = to - from;
  if (Math.abs(delta) < options.minDelta) return null;
  const raw = -delta * options.ratio;
  const offset =
    options.maxOffset === undefined
      ? raw
      : Math.sign(raw) * Math.min(Math.abs(raw), options.maxOffset);
  return {
    channel,
    keys: [{ atMs: 0, value: from + offset }],
    durationMs: options.leadMs,
  };
}
