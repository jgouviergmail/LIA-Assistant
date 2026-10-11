/** Whole-body acting is a single timed performance, including the facial answer. */
import type { BodyMotionSpace } from '../body-motion-geometry';
import type { ActingProfile } from './acting-profile';
import { absolute, relative } from './choreo';
import { sketchDurationMs, sketchTapes, type SketchName } from './sketches';
import type { ChannelKey } from './channels';
import type { Tape } from './tape';

const FACE = { frequency: 3.8, damping: 0.9 };
const LID = { frequency: 6.2, damping: 0.72 };
function bound(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value)) + 0;
}

function directedValue(
  tape: Tape,
  value: number,
  profile: ActingProfile,
  space: BodyMotionSpace
): number {
  if (tape.channel === 'bodyX') return bound(value * profile.bodyAmplitude, space.minX, space.maxX);
  if (tape.channel === 'bodyY') return bound(value * profile.bodyAmplitude, space.minY, space.maxY);
  if (tape.channel === 'bodySx' || tape.channel === 'bodySy')
    return bound(1 + (value - 1) * profile.bodyAmplitude, 0.35, 1.3);
  return tape.relative ? value * profile.faceAmplitude + 0 : value;
}

/** Keeps body geometry bounded and its five axes on one pace, including recovery. */
export function directActingTapes(
  tapes: readonly Tape[],
  profile: ActingProfile,
  space: BodyMotionSpace
): Tape[] {
  return tapes.map(tape => ({
    ...tape,
    keys: tape.keys.map(key => ({
      atMs: Math.round(key.atMs * profile.pace),
      value: directedValue(tape, key.value, profile, space),
    })),
    durationMs:
      tape.durationMs === undefined ? undefined : Math.round(tape.durationMs * profile.pace),
  }));
}

function signatureAnswer(profile: ActingProfile, duration: number): Tape[] {
  const home = duration - 650;
  const answer = (
    channel: ChannelKey,
    keys: readonly (readonly [number, number])[],
    absoluteValue = false
  ) => (absoluteValue ? absolute : relative)(channel, [...keys, [home, 0]], duration, FACE);
  switch (profile.identity) {
    case 'nimbo':
      return [
        answer(
          'headPitch',
          [
            [350, -0.22],
            [850, 0.35],
            [1200, -0.55],
            [1500, -0.55],
            [1800, 0.1],
            [2220, 0],
          ],
          true
        ),
        answer('browArcL', [
          [850, -0.18],
          [1200, -0.25],
          [1510, 0.16],
        ]),
      ];
    case 'orbit':
      return [
        answer(
          'gazeX',
          [
            [3800, -0.35],
            [4100, 0.3],
          ],
          true
        ),
        answer('browYL', [
          [3800, -0.1],
          [4100, -0.04],
        ]),
      ];
    case 'bip':
      return [
        absolute(
          'blinkR',
          [
            [2300, 1],
            [2510, 0],
          ],
          2790,
          LID
        ),
        answer('mouthCurve', [
          [2300, 0.34],
          [2670, 0.12],
        ]),
      ];
    case 'boulon':
      return [
        answer('mouthCurve', [
          [2200, 0.42],
          [2550, 0.28],
          [3050, 0.12],
        ]),
        answer('browArcL', [
          [2200, 0.3],
          [2550, 0.18],
        ]),
      ];
    default:
      return [];
  }
}

export function actingSketchTapes(
  name: SketchName,
  profile: ActingProfile,
  space: BodyMotionSpace,
  random: () => number
): Tape[] {
  const authored = sketchTapes(name, space, random);
  const answer =
    name === profile.signature ? signatureAnswer(profile, sketchDurationMs(authored)) : [];
  return directActingTapes([...authored, ...answer], profile, space);
}
