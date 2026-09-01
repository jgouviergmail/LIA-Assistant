/**
 * The rig runtime — behavioural tests of the MOTION itself.
 *
 * This is the capability the previous system did not have: the CSS could only
 * be tested for the state it declared, never for what the eyes did between two
 * states. Here the clock is an argument, so every animation principle the rig
 * claims to implement is asserted frame by frame.
 */

import { describe, it, expect } from 'vitest';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { resolveLoops, resolvePose } from '@/components/eyes/rig/poses';
import {
  CHANNEL_KEYS,
  isDerived,
  restChannelValues,
  type ChannelKey,
  type ChannelValues,
} from '@/components/eyes/rig/channels';
import type { Tape } from '@/components/eyes/rig/tape';

const FRAME_MS = 16;

/** Run the rig and collect one channel's value on every frame. */
function trace(rig: EyeRig, channel: ChannelKey, frames: number, dtMs = FRAME_MS): number[] {
  const values: number[] = [];
  for (let index = 0; index < frames; index += 1) {
    rig.step(dtMs);
    values.push(rig.values()[channel]);
  }
  return values;
}

/** The channels a POSE declares — derived ones are computed from the motion,
 * so they have no pose value to compare against. */
function posedOnly(values: Readonly<ChannelValues>): Partial<ChannelValues> {
  const subset: Partial<ChannelValues> = {};
  CHANNEL_KEYS.filter(key => !isDerived(key)).forEach(key => {
    subset[key] = values[key];
  });
  return subset;
}

function settledRig(): EyeRig {
  return createEyeRig({ initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' } });
}

describe('createEyeRig', () => {
  it('boots already settled on its pose — no animation on first paint', () => {
    const rig = createEyeRig({ initial: { expression: 'sad', styleId: 'cozmo', family: 'calm' } });
    expect(posedOnly(rig.values())).toEqual(posedOnly(resolvePose('sad', 'cozmo')));
  });

  it('starts neutral by default, already breathing', () => {
    // Every channel the idle loops do NOT ride sits exactly on its rest value.
    // The ones they do ride are already off it on the very first frame, and
    // must be: the moving hold is what keeps a resting face from freezing.
    const values = createEyeRig().values();
    const rest = restChannelValues();
    // Budget per channel = the sum of the amplitudes riding it, in that
    // channel's own unit (a rotation drifts in degrees, a mass in units).
    const budget = new Map<ChannelKey, number>();
    resolveLoops('neutral', 'calm').forEach(loop => {
      budget.set(loop.channel, (budget.get(loop.channel) ?? 0) + Math.abs(loop.amplitude));
    });
    CHANNEL_KEYS.filter(key => !isDerived(key) && !budget.has(key)).forEach(key => {
      expect({ key, value: values[key] }).toEqual({ key, value: rest[key] });
    });
    expect([...budget.keys()].some(key => values[key] !== rest[key])).toBe(true);
    budget.forEach((amplitude, key) => {
      expect({ key, within: Math.abs(values[key] - rest[key]) <= amplitude + 1e-9 }).toEqual({
        key,
        within: true,
      });
    });
  });

  it('ignores a non-positive dt — the clock does not advance', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
    rig.step(FRAME_MS);
    const before = { ...rig.values() };
    rig.step(0);
    expect(rig.values()).toEqual(before);
    rig.step(-8);
    expect(rig.values()).toEqual(before);
  });

  it('derives its computed channels before anyone can read them', () => {
    // The constructor copies POSE targets into the output, and a derived
    // channel has none: without an initial derivation the first painted frame
    // would carry a resting mouth curve with a zero arc.
    const rig = createEyeRig();
    expect(rig.values().mouthArc).toBeGreaterThan(0);
    expect(rig.values().mouthFlip).toBe(1);
  });
});

describe('pose changes', () => {
  it('converges onto the new pose', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'syL', 120);
    const target = resolvePose('anger', 'cozmo');
    expect(rig.values().syL).toBeCloseTo(target.syL, 3);
    expect(rig.values().rotL).toBeCloseTo(target.rotL, 2);
    expect(rig.values().lidTopL).toBeCloseTo(target.lidTopL, 1);
  });

  it('ANTICIPATES: the eye pulls away before it commits', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'joy', styleId: 'cozmo', family: 'calm' });
    // Joy squashes to 0.55, so the anticipation must first push ABOVE 1.
    const lead = trace(rig, 'syL', 7);
    expect(Math.max(...lead)).toBeGreaterThan(1.005);
    trace(rig, 'syL', 120);
    expect(rig.values().syL).toBeCloseTo(resolvePose('joy', 'cozmo').syL, 2);
  });

  it('does NOT anticipate a reflex — a startle that telegraphs itself is none', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'surprise', styleId: 'cozmo', family: 'calm' });
    const lead = trace(rig, 'syL', 12);
    expect(Math.min(...lead)).toBeGreaterThanOrEqual(1);
  });

  it('lands joy with a POP the pose alone could never produce', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'joy', styleId: 'cozmo', family: 'calm' });
    const mass = trace(rig, 'mass', 40);
    expect(Math.min(...mass)).toBeLessThan(0.99);
    expect(Math.max(...mass)).toBeGreaterThan(1.02);
    // ...then it hands the mass back to the breathing loop, which never
    // freezes on exactly 1 — joy keeps breathing once it has landed.
    trace(rig, 'mass', 200);
    expect(Math.abs(rig.values().mass - 1)).toBeLessThan(0.02);
  });

  it('snaps the scale anchor instead of sliding it (no false drift)', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'sad', styleId: 'cozmo', family: 'calm' });
    rig.step(FRAME_MS);
    expect(rig.values().oyL).toBe(100);
  });

  it('keeps the motion CONTINUOUS when an emotion interrupts another', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'joy', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'syL', 10);
    const before = rig.values().syL;
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
    rig.step(FRAME_MS);
    // No teleport: the change of mind is a change of TARGET, not of position.
    expect(Math.abs(rig.values().syL - before)).toBeLessThan(0.05);
  });

  it('re-resolves the pose when only the style changes', () => {
    const rig = createEyeRig({ initial: { expression: 'joy', styleId: 'cozmo', family: 'calm' } });
    rig.setPose({ expression: 'joy', styleId: 'traits', family: 'calm' });
    trace(rig, 'syL', 200);
    expect(rig.values().syL).toBeCloseTo(1, 3);
  });

  it('does nothing at all when the pose is unchanged', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'neutral', styleId: 'cozmo', family: 'calm' });
    rig.step(FRAME_MS);
    expect(rig.values().syL).toBe(1);
  });
});

describe('gaze', () => {
  it('travels to an aim and eases back to centre', () => {
    const rig = settledRig();
    // Tolerances leave room for the moving hold: a settled gaze still drifts
    // by a few hundredths, on purpose (see the "moving hold" test below).
    rig.setGaze({ x: 1, y: -0.5 });
    trace(rig, 'gazeX', 80);
    expect(rig.values().gazeX).toBeCloseTo(1, 1);
    expect(rig.values().gazeY).toBeCloseTo(-0.5, 1);
    rig.setGaze(null);
    trace(rig, 'gazeX', 80);
    expect(rig.values().gazeX).toBeCloseTo(0, 1);
  });
});

describe('loops', () => {
  it('breathes on a calm pose, and never settles while it does', () => {
    const rig = settledRig();
    const mass = trace(rig, 'mass', 300);
    expect(Math.max(...mass) - Math.min(...mass)).toBeGreaterThan(0.01);
    expect(rig.isAwake()).toBe(true);
  });

  it('goes to sleep when nothing moves any more (battery, not laziness)', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'focused', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'syL', 300);
    expect(rig.isAwake()).toBe(false);
  });
});

describe('tapes', () => {
  const BLINK: Tape = {
    channel: 'blinkL',
    keys: [
      { atMs: 0, value: 1 },
      { atMs: 130, value: 0 },
    ],
    spring: { frequency: 6, damping: 0.75 },
  };

  it('closes and reopens the lid, then hands the channel back', () => {
    const rig = settledRig();
    rig.play(BLINK);
    const closure = trace(rig, 'blinkL', 10);
    expect(Math.max(...closure)).toBeGreaterThan(0.5);
    trace(rig, 'blinkL', 200);
    expect(rig.values().blinkL).toBeCloseTo(0, 3);
  });

  it('overshoots on reopening — the rebound that gives a blink its flesh', () => {
    const rig = settledRig();
    rig.play(BLINK);
    const whole = trace(rig, 'blinkL', 40);
    expect(Math.min(...whole)).toBeLessThan(0);
  });

  it('lets the last tape on a channel win', () => {
    const rig = settledRig();
    rig.play(BLINK, { channel: 'blinkL', keys: [{ atMs: 0, value: 0.3 }], durationMs: 200 });
    rig.step(FRAME_MS);
    expect(rig.values().blinkL).toBeLessThan(0.3);
  });

  it('a REFLEX pre-empts every playing beat', () => {
    // A startle landing on a half-played flourish reads as two characters
    // arguing over one face. The reflex takes it outright.
    const rig = settledRig();
    rig.play(BLINK);
    trace(rig, 'blinkL', 3);
    expect(rig.values().blinkL).toBeGreaterThan(0.2);
    rig.setPose({ expression: 'surprise', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'blinkL', 20);
    expect(rig.values().blinkL).toBeCloseTo(0, 2);
  });

  it('a non-reflex expression lets a beat finish (overlapping action)', () => {
    const rig = settledRig();
    rig.play(BLINK);
    trace(rig, 'blinkL', 3);
    rig.setPose({ expression: 'tender', styleId: 'cozmo', family: 'calm' });
    rig.step(FRAME_MS);
    expect(rig.values().blinkL).toBeGreaterThan(0.2);
  });
});

describe('reduced motion', () => {
  it('snaps to the pose, runs no loop and never asks for a frame', () => {
    const rig = settledRig();
    rig.setReducedMotion(true);
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
    rig.step(FRAME_MS);
    const target = resolvePose('anger', 'cozmo');
    expect(rig.values().syL).toBe(target.syL);
    expect(rig.values().mass).toBe(1);
    expect(rig.isAwake()).toBe(false);
  });

  it('refuses to play beats', () => {
    const rig = createEyeRig({ reducedMotion: true });
    rig.play({ channel: 'blinkL', keys: [{ atMs: 0, value: 1 }], durationMs: 200 });
    rig.step(FRAME_MS);
    expect(rig.values().blinkL).toBe(0);
  });

  it('settles the pose the moment it is switched on', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'sleep', styleId: 'cozmo', family: 'drowsy' });
    rig.step(FRAME_MS);
    rig.setReducedMotion(true);
    expect(rig.values().lidTopL).toBe(resolvePose('sleep', 'cozmo').lidTopL);
  });
});

describe('gaze travel intent', () => {
  it('makes a saccade arrive sooner than an eased return', () => {
    const jump = createEyeRig();
    jump.setGaze({ x: 1, y: 0 }, { frequency: 7.5, damping: 0.95 });
    const glide = createEyeRig();
    glide.setGaze({ x: 1, y: 0 }, { frequency: 1.6, damping: 0.95 });
    for (let frame = 0; frame < 6; frame += 1) {
      jump.step(16);
      glide.step(16);
    }
    expect(jump.values().gazeX).toBeGreaterThan(glide.values().gazeX);
  });

  it('falls back to the expression dynamics when no travel time is given', () => {
    const rig = createEyeRig();
    rig.setGaze({ x: 1, y: 0 });
    for (let frame = 0; frame < 80; frame += 1) rig.step(16);
    expect(rig.values().gazeX).toBeCloseTo(1, 1);
  });
});

describe('the animator principles the springs alone do not give', () => {
  it('ARCS a horizontal gaze: it rides up mid-travel, not along a rail', () => {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    // `focused` neither breathes nor drifts, so the only vertical motion here
    // can be the arc.
    rig.setGaze({ x: 1, y: 0 });
    const vertical = trace(rig, 'gazeY', 40);
    expect(Math.min(...vertical)).toBeLessThan(-0.02);
    // ...and the arc closes: nothing of it survives the landing.
    trace(rig, 'gazeY', 200);
    expect(rig.values().gazeY).toBeCloseTo(0, 3);
  });

  it('STRETCHES along the travel and relaxes at rest', () => {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    expect(rig.values().stretchK).toBe(0);
    rig.setGaze({ x: 1, y: 0 }, { frequency: 6, damping: 0.9 });
    const amounts = trace(rig, 'stretchK', 30);
    expect(Math.max(...amounts)).toBeGreaterThan(0.01);
    // A purely horizontal move deforms along the horizontal axis.
    expect(Math.abs(rig.values().stretchA)).toBeLessThan(30);
    trace(rig, 'stretchK', 200);
    expect(rig.values().stretchK).toBeCloseTo(0, 3);
  });

  it('holds the stretch AXIS while the eyes are too slow to have one', () => {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    rig.setGaze({ x: 1, y: 0 });
    trace(rig, 'stretchA', 30);
    const settledAngle = rig.values().stretchA;
    trace(rig, 'stretchA', 300);
    // No jitter once the motion dies: the angle is held, never recomputed
    // from numerical noise (that would rewrite the DOM on every idle frame).
    expect(rig.values().stretchA).toBe(settledAngle);
  });

  it('OVERLAPS the departures: the lids leave after the pose does', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm' });
    // Two frames in: the willed motion has started, the lid has not.
    trace(rig, 'syL', 2);
    expect(rig.values().lidTopL).toBe(0);
    expect(Math.abs(rig.values().syL - 1)).toBeGreaterThan(0.001);
    // The lid does catch up.
    trace(rig, 'lidTopL', 140);
    expect(rig.values().lidTopL).toBeCloseTo(34, 0);
  });

  it('EXAGGERATES by mood: a lively scowl is bigger and quicker than a drowsy one', () => {
    const amplitudeFor = (family: 'lively' | 'drowsy') => {
      const rig = createEyeRig({ initial: { expression: 'neutral', styleId: 'cozmo', family } });
      rig.setPose({ expression: 'anger', styleId: 'cozmo', family });
      trace(rig, 'rotL', 200);
      return rig.values().rotL;
    };
    expect(amplitudeFor('lively')).toBeGreaterThan(amplitudeFor('drowsy'));

    const progressAfter = (family: 'lively' | 'drowsy') => {
      const rig = createEyeRig({ initial: { expression: 'neutral', styleId: 'cozmo', family } });
      rig.setPose({ expression: 'sad', styleId: 'cozmo', family });
      return trace(rig, 'syL', 14)[13];
    };
    // Sadness closes downward from 1: the quicker family is FURTHER along.
    expect(progressAfter('lively')).toBeLessThan(progressAfter('drowsy'));
  });

  it('MOVING HOLD: a settled idle face never actually stops', () => {
    const rig = settledRig();
    trace(rig, 'gazeX', 400);
    const settled = trace(rig, 'gazeX', 400);
    const spread = Math.max(...settled) - Math.min(...settled);
    expect(spread).toBeGreaterThan(0.005);
    expect(spread).toBeLessThan(0.1);
  });

  it('...but a concentrating face DOES hold still', () => {
    const rig = settledRig();
    rig.setPose({ expression: 'focused', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'gazeX', 300);
    const held = trace(rig, 'gazeX', 200);
    expect(Math.max(...held) - Math.min(...held)).toBe(0);
  });
});

describe('squash & stretch calibration', () => {
  /** The spring the host builds for a travel time (mirrors `useEyesRig`). */
  const springForTravel = (ms: number) => ({ frequency: 1.057 / (ms / 1000), damping: 0.95 });

  function peakStretch(travelMs: number, amplitude: number): number {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    rig.setGaze({ x: amplitude, y: 0 }, springForTravel(travelMs));
    return Math.max(...trace(rig, 'stretchK', 60));
  }

  it('reads on a normal gaze move without ever caricaturing', () => {
    // Measured in a browser (2026-08-31): the previous gain peaked at 1.6 %,
    // which is present in the numbers and invisible to a viewer.
    const normal = peakStretch(380, 1);
    expect(normal).toBeGreaterThan(0.04);
    expect(normal).toBeLessThan(0.1);
  });

  it('stays inside its cap for the FASTEST beat the system can produce', () => {
    // A saccade is the shortest travel the idle life schedules (140 ms). The
    // cap is what stops a fast dart from stretching the eyes into ribbons.
    const saccade = peakStretch(140, 0.4);
    expect(saccade).toBeLessThanOrEqual(0.14);
  });

  it('deforms along the direction of travel, whichever way that is', () => {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    rig.setGaze({ x: 0, y: 1 });
    trace(rig, 'stretchA', 8);
    // A purely vertical move deforms vertically (90 degrees), not sideways.
    expect(Math.abs(rig.values().stretchA)).toBeCloseTo(90, 0);
  });
});

describe('reduced motion is honoured on EVERY entry point', () => {
  it('starts no pattern when the rig is BORN under the preference', () => {
    // The `setPose` path guarded this from the start; the constructor did not,
    // so a rig created on a searching pose would sit on its first fixation —
    // staring off to one side instead of looking ahead.
    const rig = createEyeRig({
      initial: { expression: 'searching', styleId: 'cozmo', family: 'calm' },
      reducedMotion: true,
    });
    trace(rig, 'gazeX', 60);
    expect(rig.values().gazeX).toBe(0);
    expect(rig.isAwake()).toBe(false);
  });
});

describe('emphasis — how forcefully a pose lands', () => {
  function settledRot(emphasis: number): number {
    const rig = createEyeRig();
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm', emphasis });
    trace(rig, 'rotL', 220);
    return rig.values().rotL;
  }

  it('scales the SAME expression instead of choosing another', () => {
    const plain = settledRot(1);
    const emphatic = settledRot(1.3);
    const quiet = settledRot(0.8);
    expect(emphatic).toBeGreaterThan(plain);
    expect(quiet).toBeLessThan(plain);
    // Same sign, same emotion: a bigger scowl is still a scowl.
    expect(Math.sign(emphatic)).toBe(Math.sign(quiet));
  });

  it('leaves the pose exactly as authored when nothing was emphatic', () => {
    expect(settledRot(1)).toBeCloseTo(resolvePose('anger', 'cozmo').rotL, 3);
  });

  it('also lands quicker, at half strength', () => {
    const progress = (emphasis: number) => {
      const rig = createEyeRig();
      rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm', emphasis });
      return trace(rig, 'lidTopL', 12)[11];
    };
    expect(progress(1.4)).toBeGreaterThan(progress(1));
  });

  it('re-lands the pose when only the emphasis changes', () => {
    const rig = createEyeRig();
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm', emphasis: 1 });
    trace(rig, 'rotL', 220);
    const before = rig.values().rotL;
    rig.setPose({ expression: 'anger', styleId: 'cozmo', family: 'calm', emphasis: 1.35 });
    trace(rig, 'rotL', 220);
    expect(rig.values().rotL).toBeGreaterThan(before);
  });
});
