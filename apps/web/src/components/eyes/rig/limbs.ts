/** Anatomical acting composes through the rig's existing poses, loops and tapes. */
import type { EyeExpression } from '../expression-engine';
import type { RigCharacterId } from './acting-profile';
import { LIMB_CHANNELS, type ChannelKey, type ChannelValues, type LimbChannel } from './channels';
import { finiteUnit, type ActingContext } from './direction';
import type { LoopSpec } from './loops';

const FULL_BODY: ReadonlySet<RigCharacterId> = new Set(['bip', 'boulon', 'oscar']);
const SOFT_BODY: ReadonlySet<RigCharacterId> = new Set(['moss', 'lumen']);
const APPENDAGES: ReadonlySet<RigCharacterId> = new Set(['spirit', 'nimbo']);
const JOINTS: ReadonlySet<ChannelKey> = new Set(LIMB_CHANNELS);

export function isLimbChannel(channel: ChannelKey): channel is LimbChannel {
  return JOINTS.has(channel);
}

/** Orbit's lateral silhouette is its ring; eye-only styles have no body anatomy. */
export function hasLimb(identity: RigCharacterId, channel: LimbChannel): boolean {
  return (
    FULL_BODY.has(identity) ||
    (SOFT_BODY.has(identity) && (channel.startsWith('arm') || channel.startsWith('foot'))) ||
    (APPENDAGES.has(identity) && channel.startsWith('arm'))
  );
}

/** Shared safety envelope; the renderer may impose tighter anatomical joint limits. */
export const LIMB_LIMITS: Readonly<Record<LimbChannel, number>> = {
  armL: 18,
  armR: 18,
  wristL: 14,
  wristR: 14,
  legL: 8,
  legR: 8,
  footL: 10,
  footR: 10,
};

function bounded(value: number, limit: number): number {
  return Number.isFinite(value) ? Math.max(-limit, Math.min(limit, value)) + 0 : 0;
}

/** Pose is below scene/speech tapes in the runtime's native priority order. */
export function limbPose(
  pose: ChannelValues,
  expression: EyeExpression,
  context: ActingContext,
  identity: RigCharacterId,
  intensity: number
): ChannelValues {
  let opening = 0;
  let thought = 0;
  if (
    expression !== 'speaking' &&
    (context.activity || ['thinking', 'searching', 'focused'].includes(expression))
  )
    thought = 1;
  else if (expression === 'attentive') opening = 6;
  else if (expression === 'joy' || expression === 'surprise') opening = 10;
  else if (expression === 'sad' || expression === 'sleepy') opening = -2;
  // A speaking pose releases completely between phrases; emotional tone does not
  // leave the hands permanently raised throughout an answer.
  if (expression !== 'speaking' && expression !== 'sleep')
    opening += finiteUnit(context.pleasure) * 2 + finiteUnit(context.arousal) * 0.7;
  const force = Number.isFinite(intensity) ? Math.max(0, Math.min(2, intensity)) : 1;
  const next = {
    ...pose,
    armL: (opening + thought * 6) * force,
    armR: (-opening - thought) * force,
    wristL: (opening * 0.3 + thought * 8) * force,
    wristR: -opening * 0.25 * force,
    legL: 0,
    legR: 0,
    footL: 0,
    footR: 0,
  };
  clampLimbOutput(next, identity, false);
  return next;
}

/** One breath reaches the arms then wrists; resting feet retain ground contact. */
export function limbLoops(identity: RigCharacterId, loops: readonly LoopSpec[]): LoopSpec[] {
  const hands: readonly (readonly [LimbChannel, number, number])[] = [
    ['armL', 105, 0.96],
    ['armR', -90, 0.95],
    ['wristL', 65, 0.92],
    ['wristR', -55, 0.91],
  ];
  return loops
    .filter(loop => loop.channel === 'mass')
    .flatMap(loop =>
      hands
        .filter(([channel]) => hasLimb(identity, channel))
        .map(([channel, gain, trail]) => ({
          ...loop,
          channel,
          amplitude: loop.amplitude * gain,
          phase: loop.phase + trail,
        }))
    );
}

/** No integration here: absolute clamps cannot accumulate during the idle path. */
export function clampLimbOutput(
  output: ChannelValues,
  identity: RigCharacterId,
  reducedMotion: boolean
): void {
  for (const channel of LIMB_CHANNELS)
    output[channel] =
      reducedMotion || !hasLimb(identity, channel)
        ? 0
        : bounded(output[channel], LIMB_LIMITS[channel]);
}
