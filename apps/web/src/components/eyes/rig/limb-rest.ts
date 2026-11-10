/** Anatomical rest beats follow facial intent and preserve the stance foot. */
import { limbArticulation, type RigCharacterId } from './acting-profile';
import { LIMB_CHANNELS, type LimbChannel } from './channels';
import type { MouthMimic } from './life';
import { hasLimb } from './limbs';
import { tapeDurationMs, type Tape } from './tape';

type RestPose = readonly [
  arm: number,
  otherArm: number,
  wrist: number,
  otherWrist: number,
  foot: number,
];
const POSES: Record<MouthMimic, RestPose | null> = {
  grin: [8, -5, 4, -2, 0],
  gasp: [12, -10, -5, 4, 0],
  sulk: [-4, 3, -3, 2, 0],
  hmm: [7, -1, 8, -1, 0],
  smirk: [6, -2, 4, -1, 5],
  pucker: [3, -2, 2, -1, 0],
  giggle: [9, -7, 4, -3, 7],
  wiggle: null,
  smack: null,
};

/** Side and duration already belong to the facial phrase; no new entropy or clock. */
export function limbRestTapes(
  facial: readonly Tape[],
  identity: RigCharacterId,
  side: 1 | -1,
  mimic: MouthMimic
): Tape[] {
  const pose = POSES[mimic];
  if (!pose || !hasLimb(identity, 'armL')) return [];
  const { accent, wristLag, recovery } = limbArticulation(identity);
  const hold = Math.min(
    1100,
    Math.max(700, ...facial.filter(tape => !tape.release).map(tapeDurationMs))
  );
  const left: Record<LimbChannel, number> = {
    armL: pose[0],
    armR: pose[1],
    wristL: pose[2],
    wristR: pose[3],
    legL: -pose[4] * 0.4,
    legR: 0,
    footL: pose[4],
    footR: 0,
  };
  const values: Record<LimbChannel, number> =
    side > 0
      ? left
      : {
          armL: -left.armR,
          armR: -left.armL,
          wristL: -left.wristR,
          wristR: -left.wristL,
          legL: -left.legR,
          legR: -left.legL,
          footL: -left.footR,
          footR: -left.footL,
        };
  const durationMs = hold + 1200;
  const tapes: Tape[] = LIMB_CHANNELS.filter(channel => hasLimb(identity, channel)).map(channel => {
    const foot = channel.startsWith('foot') || channel.startsWith('leg');
    const trail = channel.startsWith('wrist') ? wristLag : 0;
    const value = values[channel];
    const hand = value * accent;
    return {
      channel,
      relative: true,
      interpolation: 'smooth',
      durationMs,
      spring: { frequency: foot ? 3.8 : trail ? 3 : 3.5, damping: 1 },
      keys: foot
        ? [
            { atMs: 0, value: 0 },
            { atMs: 420, value: 0 },
            { atMs: 650, value },
            { atMs: hold, value },
            { atMs: hold + 250, value: 0 },
          ]
        : [
            { atMs: 0, value: 0 },
            { atMs: 90 + trail, value: -hand * 0.06 },
            { atMs: 260 + trail, value: hand },
            { atMs: hold, value: hand },
            { atMs: hold + Math.round(500 * recovery) + trail, value: 0 },
          ],
    };
  });
  if (pose[4] && hasLimb(identity, 'footL'))
    tapes.push({
      channel: 'bodySupportSide',
      relative: true,
      interpolation: 'smooth',
      durationMs,
      spring: { frequency: 4.6, damping: 1 },
      keys: [
        { atMs: 0, value: 0 },
        { atMs: 200, value: side },
        { atMs: hold + 600, value: side },
        { atMs: hold + 950, value: 0 },
      ],
    });
  return tapes;
}
