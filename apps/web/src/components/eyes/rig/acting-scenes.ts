/** Whole-body acting is a single timed performance, including the facial answer. */
import type { BodyMotionSpace } from '../body-motion-geometry';
import type { ActingProfile } from './acting-profile';
import { sketchTapes, type SketchName } from './sketches';
import { bodySketchTapes, isBodySketchName } from './body-sketches';
import type { Tape } from './tape';
import { hasLimb, isLimbChannel } from './limbs';

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
  if (tape.channel === 'bodyRoll' || tape.channel === 'tilt')
    return value * profile.bodyAmplitude + 0;
  if (tape.channel === 'bodySx' || tape.channel === 'bodySy')
    return bound(1 + (value - 1) * profile.bodyAmplitude * profile.elasticity, 0.35, 1.3);
  if (tape.channel.startsWith('body') || isLimbChannel(tape.channel)) return value;
  return tape.relative ? value * profile.faceAmplitude + 0 : value;
}

/** Keeps body geometry bounded and its five axes on one pace, including recovery. */
export function directActingTapes(
  tapes: readonly Tape[],
  profile: ActingProfile,
  space: BodyMotionSpace
): Tape[] {
  return tapes
    .filter(tape => !isLimbChannel(tape.channel) || hasLimb(profile.identity, tape.channel))
    .map(tape => ({
      ...tape,
      keys: tape.keys.map(key => ({
        atMs: Math.round(key.atMs * profile.pace),
        value: directedValue(tape, key.value, profile, space),
      })),
      durationMs:
        tape.durationMs === undefined ? undefined : Math.round(tape.durationMs * profile.pace),
    }));
}

export function actingSketchTapes(
  name: SketchName,
  profile: ActingProfile,
  space: BodyMotionSpace,
  random: () => number
): Tape[] {
  const authored = isBodySketchName(name)
    ? bodySketchTapes(name, space, random, profile.identity)
    : sketchTapes(name, space, random);
  return directActingTapes(authored, profile, space);
}
