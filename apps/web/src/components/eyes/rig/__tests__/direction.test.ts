import { describe, expect, it } from 'vitest';

import { createEyeRig } from '../runtime';
import { createLifeRandom } from '../life';
import { NEUTRAL_CONTEXT } from '../direction';
import { EYE_STYLE_IDS } from '../../eye-styles';
import { ACTIVITY_FAMILIES } from '../../activity';
import { CHANNEL_KEYS } from '../channels';
import { pickMimic, type MouthMimic } from '../life';

describe('one character, three timescales', () => {
  it.each(ACTIVITY_FAMILIES)(
    'keeps %s activity finite and silent at different frame rates',
    activity => {
      for (const hz of [30, 60, 120]) {
        const rig = createEyeRig({
          initial: { expression: 'attentive', styleId: 'smiley', family: 'calm' },
          lifeRandom: createLifeRandom(42),
        });
        rig.setContext({ ...NEUTRAL_CONTEXT, activity });
        for (let i = 0; i < hz * 15; i++) rig.step(1000 / hz);
        expect(CHANNEL_KEYS.every(key => Number.isFinite(rig.values()[key]))).toBe(true);
        expect(rig.values().mouthOpen).toBeLessThan(0.03);
        expect(rig.sketchClock().played).toBe(0);
      }
    }
  );

  it('completes varied scenes during thirty minutes of rest without growing history', () => {
    const rig = createEyeRig({ lifeRandom: createLifeRandom(421) });
    for (let i = 0; i < 18_000; i++) {
      rig.step(100);
      if (i % 100 === 0)
        expect(CHANNEL_KEYS.every(key => Number.isFinite(rig.values()[key]))).toBe(true);
    }
    const clock = rig.sketchClock();
    expect(clock.completed).toBeGreaterThan(8);
    expect(clock.completed).toBeLessThan(40);
    expect(clock.recent.length).toBeLessThanOrEqual(3);
    expect(new Set(clock.recent).size).toBe(clock.recent.length);
    expect(clock.interrupted).toBe(0);
  });
  it('lets temperament bias spontaneous choices without turning them into a repeated loop', () => {
    const countSmiles = (pleasure: number) => {
      const random = createLifeRandom(347);
      let previous: MouthMimic | null = null;
      let smiles = 0;
      for (let i = 0; i < 2000; i++) {
        const mimic = pickMimic(random, previous, { ...NEUTRAL_CONTEXT, pleasure });
        expect(mimic).not.toBe(previous);
        if (mimic === 'grin' || mimic === 'giggle') smiles++;
        previous = mimic;
      }
      return smiles;
    };
    expect(countSmiles(-1)).toBeLessThan(countSmiles(1) / 2);
  });

  it('reserves the full answer hold and release for its expression, then resumes spontaneous life', () => {
    const rig = createEyeRig({ lifeRandom: createLifeRandom(19) });
    rig.setContext({ ...NEUTRAL_CONTEXT, responding: true });
    for (let i = 0; i < 1800; i++) rig.step(100);
    expect(rig.sketchClock().played).toBe(0);
    expect(rig.values().mouthOpen).toBeLessThan(0.03);
    rig.setContext(NEUTRAL_CONTEXT);
    for (let i = 0; i < 1000; i++) rig.step(100);
    expect(rig.sketchClock().completed).toBeGreaterThan(0);
  });
  it('keeps thinking quiet for two minutes, without idle mouth performances', () => {
    const rig = createEyeRig({
      initial: { expression: 'thinking', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(42),
    });
    let opening = 0;
    let mouthTravel = 0;
    let previous = rig.values().mouthX;
    for (let time = 0; time < 120_000; time += 16) {
      rig.step(16);
      opening = Math.max(opening, rig.values().mouthOpen);
      mouthTravel += Math.abs(rig.values().mouthX - previous);
      previous = rig.values().mouthX;
    }
    expect(opening).toBeLessThan(0.03);
    expect(mouthTravel).toBeLessThan(0.2);
  });

  it.each(EYE_STYLE_IDS)(
    'distinguishes a held thought from neutral on %s without opening the jaw',
    styleId => {
      const neutral = createEyeRig({
        initial: { expression: 'neutral', styleId, family: 'calm' },
        reducedMotion: true,
      });
      const thinking = createEyeRig({
        initial: { expression: 'thinking', styleId, family: 'calm' },
        reducedMotion: true,
      });
      neutral.step(16);
      thinking.step(16);
      const pose = thinking.values();
      expect(pose.syL - pose.syR).toBeGreaterThan(0.12);
      expect(Math.abs(pose.browYL - pose.browYR)).toBeGreaterThan(0.05);
      expect(pose.mouthW).toBeLessThan(neutral.values().mouthW * 0.85);
      expect(Math.abs(pose.mouthX)).toBeGreaterThan(0.04);
      expect(pose.mouthOpen).toBe(0);
      expect(pose.mouthY).toBe(0);
    }
  );

  it.each(EYE_STYLE_IDS)('carries temperament without changing %s identity', styleId => {
    const rig = createEyeRig({ initial: { expression: 'neutral', styleId, family: 'calm' } });
    const radius = rig.values().rTopL;
    rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: 0.8, curiosity: 0.9 });
    for (let i = 0; i < 150; i++) rig.step(16);
    expect(rig.values().mouthCurve).toBeGreaterThan(0.55);
    expect(rig.values().browArcL).toBeGreaterThan(0.12);
    expect(rig.values().syL).toBeLessThan(0.96);
    expect(rig.values().rTopL).toBe(radius);
    rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: -0.8 });
    for (let i = 0; i < 150; i++) rig.step(16);
    expect(rig.values().mouthCurve).toBeLessThan(-0.3);
    expect(rig.values().browRotR - rig.values().browRotL).toBeGreaterThan(14);
    expect(rig.values().mouthOpen).toBe(0);
    expect(rig.values().mouthY).toBe(0);
    expect(rig.values().rTopL).toBe(radius);
  });

  it('keeps amplified background joy subordinate to an actual task and an answer', () => {
    for (const task of [{ activity: 'communicating' as const }, { responding: true }]) {
      const rig = createEyeRig({
        initial: { expression: 'attentive', styleId: 'smiley', family: 'calm' },
        reducedMotion: true,
      });
      rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: 1, ...task });
      rig.step(16);
      expect(rig.values().mouthCurve).toBeLessThan(0.35);
      expect(rig.values().mouthOpen).toBe(0);
      expect(rig.values().mouthY).toBe(0);
    }
  });

  it('carries a legible mood change through the springs without a jump or jaw drift', () => {
    const rig = createEyeRig();
    rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: 0.8 });
    for (let i = 0; i < 300; i++) rig.step(16);
    let previous = rig.values().mouthCurve;
    rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: -0.8 });
    expect(rig.values().mouthCurve).toBe(previous);
    for (let i = 0; i < 300; i++) {
      rig.step(16);
      expect(Math.abs(rig.values().mouthCurve - previous)).toBeLessThan(0.08);
      expect(rig.values().mouthY).toBe(0);
      previous = rig.values().mouthCurve;
    }
    expect(previous).toBeLessThan(-0.3);
  });

  it('interrupts a scene when execution starts without changing the expression', () => {
    const rig = createEyeRig({
      initial: { expression: 'attentive', styleId: 'smiley', family: 'calm' },
    });
    rig.playSketch([{ channel: 'mouthOpen', keys: [{ atMs: 0, value: 0.7 }], durationMs: 5000 }]);
    rig.step(16);
    expect(rig.isPerforming()).toBe(true);
    rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'reading' });
    expect(rig.isPerforming()).toBe(false);
    for (let i = 0; i < 100; i++) rig.step(16);
    expect(rig.values().mouthOpen).toBeLessThan(0.03);
  });

  it('gives a whole scene ownership of facial channels until an actual state interrupts', () => {
    const rig = createEyeRig();
    rig.playSketch([
      {
        channel: 'mouthOpen',
        keys: [{ atMs: 0, value: 0.25 }],
        durationMs: 3000,
      },
    ]);
    rig.play({
      channel: 'mouthOpen',
      keys: [{ atMs: 0, value: 0.9 }],
      durationMs: 2000,
    });
    for (let i = 0; i < 80; i++) rig.step(16);
    expect(rig.values().mouthOpen).toBeLessThan(0.35);
    rig.setPose({ expression: 'thinking', styleId: 'cozmo', family: 'calm' });
    for (let i = 0; i < 120; i++) rig.step(16);
    expect(rig.isPerforming()).toBe(false);
    expect(rig.values().mouthOpen).toBeLessThan(0.03);
  });
});
