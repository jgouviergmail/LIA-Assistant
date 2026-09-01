/**
 * Periodic loops — the part of the motion that never arrives anywhere.
 *
 * Breathing, a shiver, a scan, the speaking bob: these were CSS `@keyframes`
 * on `transform`, which cannot coexist with a transform the rig writes every
 * frame (an animation replaces the property outright). They become ADDITIVE
 * oscillators instead: the spring resolves where the pose is going, the loop
 * rides on top of it. Nothing fights, and a loop can be phase-shifted per eye
 * — which is where the "never a metronome" rule actually lives.
 */

import type { ChannelKey } from '@/components/eyes/rig/channels';

export type Waveform = 'sine' | 'triangle' | 'hold';

export interface LoopSpec {
  readonly channel: ChannelKey;
  /** Peak deviation added to the channel, in the channel's own unit. */
  readonly amplitude: number;
  readonly periodMs: number;
  /** Phase offset in turns ([0, 1)) — the per-eye desync. */
  readonly phase: number;
  readonly waveform: Waveform;
}

/** How hard the `hold` waveform is driven into its clip — the higher, the
 * longer it dwells at each end of travel. 1.7 reproduces the ~16 % holds the
 * scan keyframe declared at each extremity. */
const HOLD_GAIN = 1.7;

/** Evaluate a waveform at phase `p` (in turns). All three start at 0 rising,
 * so a phase offset means the same thing whichever one a loop picked. */
export function waveValue(waveform: Waveform, p: number): number {
  switch (waveform) {
    case 'sine':
      return Math.sin(2 * Math.PI * p);
    case 'triangle':
      return 1 - 4 * Math.abs(((((p + 0.25) % 1) + 1) % 1) - 0.5);
    case 'hold':
      return Math.max(-1, Math.min(1, HOLD_GAIN * Math.sin(2 * Math.PI * p)));
  }
}

/** The value a loop contributes at time `tMs`. */
export function loopValue(loop: LoopSpec, tMs: number): number {
  return loop.amplitude * waveValue(loop.waveform, tMs / loop.periodMs + loop.phase);
}
