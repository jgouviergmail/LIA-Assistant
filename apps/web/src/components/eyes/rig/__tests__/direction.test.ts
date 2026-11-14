import { describe, expect, it } from 'vitest';

import { createEyeRig, type EyeRig } from '../runtime';
import { createLifeRandom } from '../life';
import { NEUTRAL_CONTEXT } from '../direction';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';
import { ACTIVITY_FAMILIES } from '../../activity';
import { CHANNEL_KEYS } from '../channels';
import {
  MOUTH_LIFE_MAX_DELAY_MS,
  MOUTH_LIFE_MIN_DELAY_MS,
  pickMimic,
  type MouthMimic,
} from '../life';

describe('one character, three timescales', () => {
  it.each(ACTIVITY_FAMILIES)(
    'keeps %s activity finite and silent at different frame rates',
    activity => {
      for (const hz of [30, 60, 120]) {
        const rig = createEyeRig({
          initial: { expression: 'attentive', styleId: 'billes', family: 'calm' },
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
  it('stands its own life aside while it follows text being written, and takes no rest from it', () => {
    const initial = { expression: 'attentive', styleId: 'billes', family: 'calm' } as const;
    const following = createEyeRig({ initial, lifeRandom: createLifeRandom(19) });
    // The oracle: a face with no life of its own, in the same state.
    const lifeless = createEyeRig({ initial });
    following.setContext({ ...NEUTRAL_CONTEXT, attending: true });
    lifeless.setContext({ ...NEUTRAL_CONTEXT, attending: true });
    // Three minutes of an answer being written, measured at 9.7 % of the short
    // answers and 36 % of the long ones interrupted by a scene (2026-11-11).
    for (let frame = 0; frame < 180_000 / 16; frame += 1) {
      // An eye beat asks the face to answer: not while it follows the text.
      if (frame % 500 === 250) following.answerIn(120);
      following.step(16);
      lifeless.step(16);
      if (frame % 25 === 0) expect(following.values()).toEqual(lifeless.values());
    }
    expect(following.sketchClock().played).toBe(0);
    expect(following.sketchClock().restedMs).toBe(0);
    following.setContext(NEUTRAL_CONTEXT);
    for (let i = 0; i < 1000; i++) following.step(100);
    expect(following.sketchClock().completed).toBeGreaterThan(0);
  });

  it('takes a whole silence before its next mimic when the writing stops, never a late one at once', () => {
    const initial = { expression: 'attentive', styleId: 'billes', family: 'calm' } as const;
    // Measured before this rule (2026-11-12, 200 seeds): a mimic held back
    // during thirty seconds of typing played 1.5 s after the last key in 199
    // cases, the tic of a face that answers every pause.
    for (let seed = 1; seed <= 40; seed += 1) {
      const rig = createEyeRig({ initial, lifeRandom: createLifeRandom(seed) });
      const lifeless = createEyeRig({ initial });
      rig.setContext({ ...NEUTRAL_CONTEXT, attending: true });
      // Long enough for a mimic to have come due and been held back.
      for (let frame = 0; frame < 30_000 / 16; frame += 1) {
        rig.step(16);
        lifeless.step(16);
      }
      rig.setContext(NEUTRAL_CONTEXT);
      // A silence, not the second or two that follows a beat: no beat was played.
      for (let elapsed = 0; elapsed < MOUTH_LIFE_MIN_DELAY_MS - 100; elapsed += 16) {
        rig.step(16);
        lifeless.step(16);
      }
      expect(rig.values(), `seed ${seed}`).toEqual(lifeless.values());
    }
  });

  /** The first frame, over `frames` steps of 16 ms, at which the living face
   * leaves the lifeless one: a mimic began. Null when it never does. */
  function firstFrameApart(rig: EyeRig, lifeless: EyeRig, frames: number): number | null {
    for (let frame = 0; frame < frames; frame += 1) {
      rig.step(16);
      lifeless.step(16);
      const living = rig.values();
      const still = lifeless.values();
      if (CHANNEL_KEYS.some(key => living[key] !== still[key])) return frame;
    }
    return null;
  }

  it('takes a whole silence before its next mimic when a click or a scroll lets go of it, never a late one at once', () => {
    const initial = { expression: 'attentive', styleId: 'billes', family: 'calm' } as const;
    for (let seed = 1; seed <= 40; seed += 1) {
      const rig = createEyeRig({ initial, lifeRandom: createLifeRandom(seed) });
      const lifeless = createEyeRig({ initial });
      // Thirty seconds of scrolling: every wheel event pauses the face's life
      // for 1.5 s, long enough for a mimic to have come due and been held back.
      for (let frame = 0; frame < 30_000 / 16; frame += 1) {
        if (frame % 16 === 0) rig.pauseLifeFor(1500);
        rig.step(16);
        lifeless.step(16);
      }
      // The last event: the pause runs out 1.5 s later, and a silence follows,
      // not the second or two that follows a beat — no beat was played.
      rig.pauseLifeFor(1500);
      const frames = Math.floor((1500 + MOUTH_LIFE_MIN_DELAY_MS - 100) / 16);
      expect(firstFrameApart(rig, lifeless, frames), `seed ${seed}`).toBeNull();
    }
  });

  it('takes a whole silence before its next mimic when the pointer leaves the face, never a late one at once', () => {
    const initial = { expression: 'attentive', styleId: 'billes', family: 'calm' } as const;
    for (let seed = 1; seed <= 40; seed += 1) {
      const rig = createEyeRig({ initial, lifeRandom: createLifeRandom(seed) });
      const lifeless = createEyeRig({ initial });
      rig.setLifePaused(true);
      for (let frame = 0; frame < 30_000 / 16; frame += 1) {
        rig.step(16);
        lifeless.step(16);
      }
      rig.setLifePaused(false);
      const frames = Math.floor((MOUTH_LIFE_MIN_DELAY_MS - 100) / 16);
      expect(firstFrameApart(rig, lifeless, frames), `seed ${seed}`).toBeNull();
    }
  });

  it('leaves a mimic its own time when the pause ends before it came due', () => {
    const initial = { expression: 'attentive', styleId: 'billes', family: 'calm' } as const;
    const frames = Math.ceil((MOUTH_LIFE_MAX_DELAY_MS + 1000) / 16);
    let played = 0;
    for (let seed = 1; seed <= 40; seed += 1) {
      const paused = createEyeRig({ initial, lifeRandom: createLifeRandom(seed) });
      const free = createEyeRig({ initial, lifeRandom: createLifeRandom(seed) });
      // A click at once: the pause is over long before the first mimic is due.
      paused.pauseLifeFor(100);
      const pausedStart = firstFrameApart(paused, createEyeRig({ initial }), frames);
      const freeStart = firstFrameApart(free, createEyeRig({ initial }), frames);
      expect(pausedStart, `seed ${seed}`).toBe(freeStart);
      if (freeStart !== null) played += 1;
    }
    // Not a vacuous equality: the mimics did play.
    expect(played).toBeGreaterThan(30);
  });

  it('drops a scene the moment the face turns to text being written, and starts none meanwhile', () => {
    const rig = createEyeRig({
      initial: { expression: 'attentive', styleId: 'billes', family: 'calm' },
    });
    rig.playSketch([{ channel: 'mouthOpen', keys: [{ atMs: 0, value: 0.7 }], durationMs: 5000 }]);
    rig.step(16);
    expect(rig.isPerforming()).toBe(true);
    rig.setContext({ ...NEUTRAL_CONTEXT, attending: true });
    expect(rig.isPerforming()).toBe(false);
    rig.playScene('double-take');
    expect(rig.isPerforming()).toBe(false);
    for (let i = 0; i < 100; i++) rig.step(16);
    expect(rig.values().mouthOpen).toBeLessThan(0.03);
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

  it.each(RIG_EYE_STYLE_IDS)(
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
      const eyeAsymmetry = pose.syL - pose.syR;
      expect(eyeAsymmetry).toBeGreaterThan(0.12);
      expect(Math.abs(pose.browYL - pose.browYR)).toBeGreaterThan(0.05);
      expect(pose.mouthW).toBeLessThan(neutral.values().mouthW * 0.85);
      expect(Math.abs(pose.mouthX)).toBeGreaterThan(0.04);
      expect(pose.mouthOpen).toBe(0);
      expect(pose.mouthY).toBe(0);
    }
  );

  it.each(RIG_EYE_STYLE_IDS)('carries temperament without changing %s identity', styleId => {
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
        initial: { expression: 'attentive', styleId: 'billes', family: 'calm' },
        reducedMotion: true,
      });
      rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: 1, ...task });
      rig.step(16);
      expect(rig.values().mouthCurve).toBeLessThan(0.35);
      expect(rig.values().mouthOpen).toBe(0);
      expect(rig.values().mouthY).toBe(0);
    }
  });

  it('keeps a character its resting smile and its temperament under a factual answer', () => {
    // A factual answer earns the face it rests on: delivered, it used to put
    // the character's smile out (measured 0.26 down to 0.12 on the bench).
    const settle = (responding: boolean) => {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
        characterId: 'boulon',
        reducedMotion: true,
      });
      rig.setContext({ ...NEUTRAL_CONTEXT, pleasure: 0.5, responding });
      rig.step(16);
      return rig.values();
    };
    const resting = settle(false);
    const answering = settle(true);
    expect(answering.mouthCurve).toBeCloseTo(resting.mouthCurve, 5);
    expect(answering.browArcL).toBeCloseTo(resting.browArcL, 5);
    expect(answering.syL).toBeCloseTo(resting.syL, 5);
  });

  it('thinks a delivered careful answer over WITH the person: the looks away belong to work', () => {
    const lookingAway = (responding: boolean) => {
      const rig = createEyeRig({ lifeRandom: createLifeRandom(7) });
      rig.setContext({ ...NEUTRAL_CONTEXT, responding });
      rig.setPose({ expression: 'thinking', styleId: 'billes', family: 'calm' });
      for (let time = 0; time < 1500; time += 16) rig.step(16);
      let travel = 0;
      let [x, y] = [rig.values().gazeX, rig.values().gazeY];
      for (let time = 0; time < 6000; time += 16) {
        rig.step(16);
        travel += Math.abs(rig.values().gazeX - x) + Math.abs(rig.values().gazeY - y);
        [x, y] = [rig.values().gazeX, rig.values().gazeY];
      }
      return travel;
    };
    expect(lookingAway(false)).toBeGreaterThan(0.3);
    expect(lookingAway(true)).toBeLessThan(0.02);
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
      initial: { expression: 'attentive', styleId: 'billes', family: 'calm' },
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
