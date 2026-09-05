/**
 * Blink and gesture tapes — including the two invariants that keep the rig
 * and the host in step: no beat outlives the state the host holds for it, and
 * every gesture the rig does NOT own is explicitly handed back to CSS.
 */

import { describe, it, expect } from 'vitest';
import {
  blinkTapes,
  GESTURE_SCALE_MIN,
  GESTURE_SCALE_SPAN,
  RIG_OWNED_GESTURES,
  tapesForGesture,
} from '@/components/eyes/rig/gestures';
import { tapeDurationMs, type Tape } from '@/components/eyes/rig/tape';
import { createEyeRig } from '@/components/eyes/rig/runtime';
import { CHANNELS } from '@/components/eyes/rig/channels';
import { resolvePose } from '@/components/eyes/rig/poses';
import { GESTURE_DURATION_MS, type IdleGesture } from '@/components/eyes/expression-engine';

const ALL_GESTURES = Object.keys(GESTURE_DURATION_MS) as IdleGesture[];
const CSS_OR_GAZE: IdleGesture[] = [
  'saccade',
  'glance',
  'flicker',
  'swap',
  'bump',
  'spin',
  'jelly',
];

describe('blinkTapes', () => {
  it('shuts both eyes, the right one trailing', () => {
    const [left, right] = blinkTapes();
    expect(left.channel).toBe('blinkL');
    expect(right.channel).toBe('blinkR');
    expect(right.keys[0].atMs).toBeGreaterThan(left.keys[0].atMs);
  });

  it('holds the channel THROUGH the reopening, so the blink spring rules it', () => {
    const [left] = blinkTapes();
    const lastKey = left.keys[left.keys.length - 1];
    expect(tapeDurationMs(left)).toBeGreaterThan(lastKey.atMs);
    expect(left.spring).toBeDefined();
  });

  it('actually closes then reopens the eye when played', () => {
    const rig = createEyeRig();
    rig.play(...blinkTapes());
    let peak = 0;
    for (let frame = 0; frame < 12; frame += 1) {
      rig.step(16);
      peak = Math.max(peak, rig.values().blinkL);
    }
    expect(peak).toBeGreaterThan(0.7);
    for (let frame = 0; frame < 60; frame += 1) rig.step(16);
    expect(rig.values().blinkL).toBeCloseTo(0, 3);
  });
});

describe('tapesForGesture', () => {
  it('hands the gaze moves and the slapstick beats back to their own systems', () => {
    CSS_OR_GAZE.forEach(gesture => expect(tapesForGesture(gesture)).toHaveLength(0));
  });

  it('owns the lid and body beats', () => {
    expect(RIG_OWNED_GESTURES).toEqual(
      expect.arrayContaining([
        'slow-blink',
        'half-blink',
        'squint',
        'bounce',
        'brow',
        'perk',
        'tilt',
        'lip-press',
        'corner-tug',
        'brow-twitch',
      ])
    );
  });

  it('never lets a beat outlive the state the host holds for it', () => {
    ALL_GESTURES.forEach(gesture => {
      const hold = GESTURE_DURATION_MS[gesture as keyof typeof GESTURE_DURATION_MS];
      tapesForGesture(gesture).forEach(tape => {
        expect(tapeDurationMs(tape)).toBeLessThanOrEqual(hold);
      });
    });
  });

  it('only ever targets real channels', () => {
    ALL_GESTURES.forEach(gesture => {
      tapesForGesture(gesture).forEach(tape => expect(CHANNELS[tape.channel]).toBeDefined());
    });
  });

  it('raises ONE brow — the asymmetry is the joke', () => {
    const brow = tapesForGesture('brow');
    expect(brow.every(tape => tape.channel.endsWith('R'))).toBe(true);
    expect(brow.every(tape => tape.relative)).toBe(true);
  });

  it('raises the BROW, not the eye under it — the organ exists now', () => {
    // The gesture predates the brow organ and used to lift the right EYE.
    const channels = tapesForGesture('brow')
      .map(tape => tape.channel)
      .sort();
    expect(channels).toEqual(['browAR', 'browArcR', 'browYR']);
    // A face that neither breathes nor drifts, so the left brow is a control.
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    const pose = resolvePose('focused', 'cozmo');
    rig.play(...tapesForGesture('brow'));
    for (let frame = 0; frame < 6; frame += 1) rig.step(16);
    expect(rig.values().browYR).toBeLessThan(pose.browYR);
    expect(rig.values().browArcR).toBeGreaterThan(pose.browArcR);
    expect(rig.values().browAR).toBeGreaterThan(pose.browAR);
    expect(rig.values().browYL).toBe(pose.browYL);
  });

  it('presses the lips: width and curve pull in together, then let go', () => {
    const press = tapesForGesture('lip-press');
    expect(press.map(tape => tape.channel).sort()).toEqual(['mouthCurve', 'mouthW']);
    press.forEach(tape => {
      expect(tape.relative).toBe(true);
      expect(tape.keys[0].value).toBeLessThan(0);
      expect(tape.keys[tape.keys.length - 1].value).toBe(0);
    });
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    const restingWidth = rig.values().mouthW;
    rig.play(...press);
    for (let frame = 0; frame < 8; frame += 1) rig.step(16);
    expect(rig.values().mouthW).toBeLessThan(restingWidth - 0.03);
    for (let frame = 0; frame < 60; frame += 1) rig.step(16);
    expect(rig.values().mouthW).toBeCloseTo(restingWidth, 2);
  });

  it('tugs ONE corner, and the brow on that side agrees a beat later', () => {
    const tug = tapesForGesture('corner-tug');
    expect(tug.map(tape => tape.channel).sort()).toEqual(['browArcL', 'browYL', 'mouthSkew']);
    tug.forEach(tape => {
      expect(tape.relative).toBe(true);
      expect(tape.keys[tape.keys.length - 1].value).toBe(0);
    });
    const corner = tug.find(tape => tape.channel === 'mouthSkew')!;
    const brow = tug.find(tape => tape.channel === 'browYL')!;
    expect(brow.keys[0].atMs).toBeGreaterThan(corner.keys[0].atMs);
    expect(brow.keys[0].value).toBeLessThan(0);
  });

  it('twitches BOTH brows — up and arched, then back, the right one trailing', () => {
    const twitch = tapesForGesture('brow-twitch');
    expect(twitch.map(tape => tape.channel).sort()).toEqual([
      'browArcL',
      'browArcR',
      'browYL',
      'browYR',
    ]);
    twitch.forEach(tape => {
      expect(tape.relative).toBe(true);
      expect(tape.keys[tape.keys.length - 1].value).toBe(0);
    });
    const left = twitch.find(tape => tape.channel === 'browYL')!;
    const right = twitch.find(tape => tape.channel === 'browYR')!;
    expect(left.keys[0].value).toBeLessThan(0);
    expect(right.keys[0].atMs).toBeGreaterThan(left.keys[0].atMs);
    // Played on a still face, it actually lifts and arches, then rests.
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    const pose = resolvePose('focused', 'cozmo');
    rig.play(...twitch);
    for (let frame = 0; frame < 8; frame += 1) rig.step(16);
    expect(rig.values().browYL).toBeLessThan(pose.browYL - 0.01);
    expect(rig.values().browArcL).toBeGreaterThan(pose.browArcL + 0.1);
    for (let frame = 0; frame < 80; frame += 1) rig.step(16);
    expect(rig.values().browYL).toBeCloseTo(pose.browYL, 2);
  });

  it('carries the FACE on the eye beats: a perk raises the brows, a squint knits them, a tilt smirks', () => {
    const channels = (gesture: IdleGesture) => tapesForGesture(gesture).map(tape => tape.channel);
    expect(channels('perk')).toEqual(
      expect.arrayContaining(['browYL', 'browYR', 'browArcL', 'browArcR'])
    );
    const perkBrow = tapesForGesture('perk').find(tape => tape.channel === 'browYL')!;
    expect(perkBrow.keys[0].value).toBeLessThan(0); // up
    expect(channels('squint')).toEqual(expect.arrayContaining(['browYL', 'browArcL', 'mouthW']));
    const squintBrow = tapesForGesture('squint').find(tape => tape.channel === 'browYL')!;
    expect(squintBrow.keys[0].value).toBeGreaterThan(0); // down
    expect(channels('tilt')).toEqual(expect.arrayContaining(['mouthSkew', 'browArcL']));
    // ...and every one of those is RELATIVE, an offset from the pose.
    (['perk', 'squint', 'tilt'] as const).forEach(gesture =>
      tapesForGesture(gesture)
        .filter(tape => tape.channel.startsWith('brow') || tape.channel.startsWith('mouth'))
        .forEach(tape => expect(tape.relative).toBe(true))
    );
  });

  it('scales the RELATIVE beats for the occasion, never an absolute closure', () => {
    const plain = tapesForGesture('slow-blink');
    const bigger = tapesForGesture('slow-blink', 1.15);
    const lid = (tapes: readonly Tape[]) => tapes.find(tape => tape.channel === 'blinkL')!;
    const mouth = (tapes: readonly Tape[]) => tapes.find(tape => tape.channel === 'mouthW')!;
    // The lid closes to exactly 1 whatever the scale: a closure is a fact.
    expect(lid(bigger).keys[0].value).toBe(lid(plain).keys[0].value);
    // The mouth's relative narrowing does scale.
    expect(mouth(bigger).keys[0].value).toBeCloseTo(mouth(plain).keys[0].value * 1.15, 6);
    // The default is exactly 1, so every other test in this file is unscaled.
    expect(tapesForGesture('brow-twitch')).toEqual(tapesForGesture('brow-twitch', 1));
    // The host's draw stays inside a nuance, never a wobble.
    expect(GESTURE_SCALE_MIN).toBeGreaterThanOrEqual(0.8);
    expect(GESTURE_SCALE_MIN + GESTURE_SCALE_SPAN).toBeLessThanOrEqual(1.2);
  });

  it('a SIGH carries the mouth: the slow blink narrows it on the exhale', () => {
    const sigh = tapesForGesture('slow-blink');
    const mouth = sigh.find(tape => tape.channel === 'mouthW');
    expect(mouth).toBeDefined();
    expect(mouth!.relative).toBe(true);
    expect(mouth!.keys[0].value).toBeLessThan(0);
    expect(tapeDurationMs(mouth!)).toBeLessThanOrEqual(GESTURE_DURATION_MS['slow-blink']);
  });

  it('a BOUNCE drags the mouth along, a beat late — follow-through', () => {
    const bounce = tapesForGesture('bounce');
    const mouth = bounce.find(tape => tape.channel === 'mouthY');
    const eye = bounce.find(tape => tape.channel === 'tyL');
    expect(mouth).toBeDefined();
    expect(mouth!.relative).toBe(true);
    expect(mouth!.keys[0].atMs).toBeGreaterThan(eye!.keys[0].atMs);
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    rig.play(...bounce);
    let peak = 0;
    for (let frame = 0; frame < 30; frame += 1) {
      rig.step(16);
      peak = Math.max(peak, Math.abs(rig.values().mouthY));
    }
    expect(peak).toBeGreaterThan(0.01);
    for (let frame = 0; frame < 80; frame += 1) rig.step(16);
    expect(rig.values().mouthY).toBeCloseTo(0, 2);
  });

  it('lifts a squashed eye RELATIVELY, never yanking it to a neutral height', () => {
    const rig = createEyeRig({ initial: { expression: 'joy', styleId: 'cozmo', family: 'calm' } });
    const restingTy = rig.values().tyL;
    rig.play(...tapesForGesture('bounce'));
    rig.step(16);
    // It went UP from joy's own height, and stayed in that neighbourhood.
    expect(rig.values().tyL).toBeLessThan(restingTy);
    expect(rig.values().tyL).toBeGreaterThan(restingTy - 0.12);
  });

  it('does not move the eyes at all when only one brow moves', () => {
    const rig = createEyeRig();
    rig.play(...tapesForGesture('brow'));
    for (let frame = 0; frame < 6; frame += 1) rig.step(16);
    expect(rig.values().tyR).toBe(0);
    expect(rig.values().tyL).toBe(0);
    expect(rig.values().syR).toBe(1);
  });
});
