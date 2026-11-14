/**
 * A mouth that opens on the voice it HEARS (ADR-294, follow-up of 2026-11-13).
 *
 * Until then a speaking face made up its syllables while the audio played: right
 * in rhythm by luck at best. Now the opening follows the level read off the sound
 * (`lib/audio/voice-envelope.ts`); the generated speech keeps the shape of the
 * words — width, curve, corners — and takes over whenever no voice is tapped.
 */
import { describe, expect, it } from 'vitest';

import { createEyeRig, type EyeRig } from '../runtime';
import { createLifeRandom } from '../life';

function run(rig: EyeRig, ms: number, each: () => void = () => undefined): void {
  for (let at = 16; at <= ms; at += 16) {
    rig.step(16);
    each();
  }
}

function speaking(voice: { level: number | null }, expression: 'speaking' | 'neutral' = 'speaking') {
  return createEyeRig({
    initial: { expression, styleId: 'billes', family: 'calm' },
    random: createLifeRandom(7),
    voiceLevel: () => voice.level,
  });
}

/** The lowest and highest a channel goes over a stretch. */
function range(rig: EyeRig, ms: number, channel: 'mouthOpen' | 'mouthW') {
  let low = Infinity;
  let high = -Infinity;
  run(rig, ms, () => {
    low = Math.min(low, rig.values()[channel]);
    high = Math.max(high, rig.values()[channel]);
  });
  return { low, high };
}

/** How long the opening takes to cross half the way between two values, in ms. */
function halfway(rig: EyeRig, from: number, to: number): number {
  const middle = (from + to) / 2;
  for (let at = 2; at <= 2000; at += 2) {
    rig.step(2);
    const open = rig.values().mouthOpen;
    if (to > from ? open >= middle : open <= middle) return at;
  }
  return Number.POSITIVE_INFINITY;
}

describe('a mouth that opens on the voice it hears', () => {
  it('stays shut in a silence and opens wide on a voice', () => {
    const voice = { level: 0 };
    const rig = speaking(voice);
    run(rig, 400);
    const silent = range(rig, 400, 'mouthOpen');
    voice.level = 1;
    const loud = range(rig, 400, 'mouthOpen');
    // Made-up syllables would open it in the silence as well.
    expect(silent.high - silent.low).toBeLessThan(0.08);
    expect(loud.high - silent.high).toBeGreaterThan(0.35);
  });

  it('holds open on a held sound and stays shut in the silence after it', () => {
    // Made-up syllables open and close on their own clock: neither holds.
    const voice = { level: 0 };
    const rig = speaking(voice);
    run(rig, 400);
    const shut = rig.values().mouthOpen;
    voice.level = 1;
    run(rig, 250);
    const held = range(rig, 300, 'mouthOpen');
    voice.level = 0;
    run(rig, 150);
    const after = range(rig, 300, 'mouthOpen');
    expect(held.low - shut).toBeGreaterThan(0.35);
    expect(after.high - shut).toBeLessThan(0.08);
  });

  it('opens on a syllable quicker than it lets go of one', () => {
    // Quick to rise, a little slower to let go: the tail of a word never chatters.
    const voice = { level: 0 };
    const rig = speaking(voice);
    run(rig, 400);
    const shut = rig.values().mouthOpen;
    voice.level = 1;
    run(rig, 600);
    const open = rig.values().mouthOpen;
    voice.level = 0;
    const letGo = halfway(rig, open, shut);
    run(rig, 600);
    voice.level = 1;
    const rise = halfway(rig, shut, open);
    expect(rise).toBeLessThan(letGo);
  });

  it('keeps the shape of its words while it follows the voice', () => {
    const voice = { level: 0.6 };
    const rig = speaking(voice);
    run(rig, 300);
    const width = range(rig, 3000, 'mouthW');
    expect(width.high - width.low).toBeGreaterThan(0.05);
  });

  it('speaks on its own when no voice is tapped', () => {
    const rig = speaking({ level: null });
    run(rig, 300);
    const made = range(rig, 2000, 'mouthOpen');
    expect(made.high - made.low).toBeGreaterThan(0.2);
  });

  it('opens nothing on a face that is not speaking', () => {
    const heard = speaking({ level: 1 }, 'neutral');
    const deaf = createEyeRig({
      initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
      random: createLifeRandom(7),
    });
    run(heard, 600);
    run(deaf, 600);
    expect(heard.values().mouthOpen).toBe(deaf.values().mouthOpen);
  });

  it('keeps a still face under reduced motion', () => {
    const voice = { level: 1 };
    const rig = createEyeRig({
      initial: { expression: 'speaking', styleId: 'billes', family: 'calm' },
      reducedMotion: true,
      voiceLevel: () => voice.level,
    });
    rig.step(16);
    const shut = rig.values().mouthOpen;
    voice.level = 0;
    rig.step(16);
    expect(rig.values().mouthOpen).toBe(shut);
  });
});
