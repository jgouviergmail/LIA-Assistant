/**
 * Blink and gesture tapes — including the two invariants that keep the rig
 * and the host in step: no beat outlives the state the host holds for it, and
 * every gesture the rig does NOT own is explicitly handed back to CSS.
 */

import { describe, it, expect } from 'vitest';
import { blinkTapes, RIG_OWNED_GESTURES, tapesForGesture } from '@/components/eyes/rig/gestures';
import { tapeDurationMs } from '@/components/eyes/rig/tape';
import { createEyeRig } from '@/components/eyes/rig/runtime';
import { CHANNELS } from '@/components/eyes/rig/channels';
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

  it('lifts a squashed eye RELATIVELY, never yanking it to a neutral height', () => {
    const rig = createEyeRig({ initial: { expression: 'joy', styleId: 'cozmo', family: 'calm' } });
    const restingTy = rig.values().tyL;
    rig.play(...tapesForGesture('bounce'));
    rig.step(16);
    // It went UP from joy's own height, and stayed in that neighbourhood.
    expect(rig.values().tyL).toBeLessThan(restingTy);
    expect(rig.values().tyL).toBeGreaterThan(restingTy - 0.12);
  });

  it('does not raise the whole face when only one brow moves', () => {
    const rig = createEyeRig();
    rig.play(...tapesForGesture('brow'));
    for (let frame = 0; frame < 6; frame += 1) rig.step(16);
    expect(rig.values().tyR).toBeLessThan(0);
    expect(rig.values().tyL).toBe(0);
  });
});
