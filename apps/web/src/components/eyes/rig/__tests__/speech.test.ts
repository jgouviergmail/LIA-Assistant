/**
 * Speech — generated, never looped.
 *
 * The previous mouth was a sum of sines: it got louder and quieter and it
 * closed on a slow envelope, but it never SAID anything, and over a long
 * answer it played the same phrase again and again. Speech has syllables,
 * words, pauses between words and longer ones between phrases, a shape per
 * word, a stressed word now and then that the brows and the head mark — and
 * no two chunks alike. The generator is pure given its entropy: the same
 * seed talks the same way, another seed talks otherwise.
 */

import { describe, it, expect } from 'vitest';

import {
  SPEECH_CHANNELS,
  SPEECH_CHUNK_MAX_MS,
  SPEECH_CHUNK_MIN_MS,
  SPEECH_OPEN_MAX,
  SPEECH_PHRASE_GAP_MIN_MS,
  SPEECH_WORD_GAP_MIN_MS,
  speechTapes,
} from '@/components/eyes/rig/speech';
import { createLifeRandom } from '@/components/eyes/rig/life';
import { resolvePatterns } from '@/components/eyes/rig/scripts';
import { resolvePose } from '@/components/eyes/rig/poses';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { tapeDurationMs, type Tape } from '@/components/eyes/rig/tape';
import type { ChannelKey } from '@/components/eyes/rig/channels';

function trace(rig: EyeRig, channel: ChannelKey, frames: number): number[] {
  const values: number[] = [];
  for (let index = 0; index < frames; index += 1) {
    rig.step(16);
    values.push(rig.values()[channel]);
  }
  return values;
}

function opening(tapes: readonly Tape[]): Tape {
  const tape = tapes.find(t => t.channel === 'mouthOpen');
  if (!tape) throw new Error('no opening tape');
  return tape;
}

describe('the chunk', () => {
  const tapes = speechTapes(createLifeRandom(21));

  it('lasts a few seconds, ends on a pause, and every tape shares its length', () => {
    const chunk = tapeDurationMs(tapes[0]);
    expect(chunk).toBeGreaterThanOrEqual(SPEECH_CHUNK_MIN_MS);
    expect(chunk).toBeLessThanOrEqual(SPEECH_CHUNK_MAX_MS);
    tapes.forEach(tape => expect(tapeDurationMs(tape)).toBe(chunk));
    // The last opening key closes the mouth: a chunk that wrapped mid-syllable
    // would cut a word in two.
    const keys = opening(tapes).keys;
    expect(keys[keys.length - 1].value).toBe(0);
    expect(chunk - keys[keys.length - 1].atMs).toBeGreaterThanOrEqual(SPEECH_WORD_GAP_MIN_MS);
  });

  it('speaks only on the channels speech owns, all relative to the pose', () => {
    tapes.forEach(tape => {
      expect({ channel: tape.channel, owned: SPEECH_CHANNELS.has(tape.channel) }).toEqual({
        channel: tape.channel,
        owned: true,
      });
      expect(tape.relative).toBe(true);
      expect(tape.spring).toBeDefined();
    });
    const channels = new Set(tapes.map(tape => tape.channel));
    ['mouthOpen', 'mouthW', 'mouthCurve', 'mouthSkew', 'mouthX', 'browYL', 'browYR'].forEach(
      channel => expect(channels.has(channel as ChannelKey)).toBe(true)
    );
  });

  it('is made of SYLLABLES: opens and closes alternate, each held about a tenth of a second', () => {
    const keys = opening(tapes).keys;
    const opens = keys.filter(key => key.value > 0.1);
    expect(opens.length).toBeGreaterThan(15);
    opens.forEach(key => expect(key.value).toBeLessThanOrEqual(SPEECH_OPEN_MAX));
    // Between two opens there is always a close.
    for (let index = 1; index < keys.length; index += 1) {
      if (keys[index].value > 0.1) expect(keys[index - 1].value).toBeLessThanOrEqual(0.1);
    }
    const holds = keys.slice(1).map((key, index) => key.atMs - keys[index].atMs);
    holds.forEach(hold => expect(hold).toBeGreaterThanOrEqual(40));
    // ...and no two syllables in a row are the same size or length.
    const sizes = opens.map(key => key.value);
    expect(new Set(sizes).size).toBeGreaterThan(sizes.length * 0.8);
  });

  it('has WORDS and PHRASES: short gaps between words, long ones between phrases', () => {
    const keys = opening(tapes).keys;
    // A gap is a stretch where the mouth is told to stay shut.
    const gaps: number[] = [];
    for (let index = 1; index < keys.length; index += 1) {
      if (keys[index - 1].value === 0) gaps.push(keys[index].atMs - keys[index - 1].atMs);
    }
    const wordGaps = gaps.filter(gap => gap < SPEECH_PHRASE_GAP_MIN_MS);
    const phraseGaps = gaps.filter(gap => gap >= SPEECH_PHRASE_GAP_MIN_MS);
    expect(wordGaps.length).toBeGreaterThanOrEqual(6);
    expect(phraseGaps.length).toBeGreaterThanOrEqual(1);
    wordGaps.forEach(gap => expect(gap).toBeGreaterThanOrEqual(SPEECH_WORD_GAP_MIN_MS));
    expect(new Set(gaps).size).toBeGreaterThan(gaps.length * 0.7);
  });

  it('STRESSES some words and not others: the brows mark them, the head nods on a few', () => {
    // A chunk with several stresses (the draw is a third of the words).
    const stressed = speechTapes(createLifeRandom(1));
    const left = stressed.find(tape => tape.channel === 'browYL');
    const right = stressed.find(tape => tape.channel === 'browYR');
    if (!left || !right) throw new Error('no brow tapes');
    const raises = left.keys.filter(key => key.value < 0);
    expect(raises.length).toBeGreaterThanOrEqual(2);
    // Fewer raises than words: a brow that lifts on every word is a tic.
    const words = opening(stressed).keys.filter(key => key.value === 0).length;
    expect(raises.length).toBeLessThan(words * 0.8);
    // The right brow trails the left and moves a hair less — and on some
    // stresses only ONE brow moves at all.
    const rightRaises = right.keys.filter(key => key.value < 0);
    expect(rightRaises.length).toBeLessThanOrEqual(raises.length);
    if (rightRaises.length > 0) expect(rightRaises[0].atMs).not.toBe(raises[0].atMs);
    const nods = stressed.find(tape => tape.channel === 'massY');
    expect(nods?.keys.some(key => key.value < 0)).toBe(true);
  });

  it('gives every WORD its own shape — width, curve, corners and a slide', () => {
    (['mouthW', 'mouthCurve', 'mouthSkew', 'mouthX'] as const).forEach(channel => {
      const tape = tapes.find(t => t.channel === channel);
      if (!tape) throw new Error(`no ${channel} tape`);
      const values = tape.keys.map(key => key.value);
      expect(new Set(values).size).toBeGreaterThan(5);
      // ...and the shape relaxes to the pose on a phrase pause.
      expect(values).toContain(0);
    });
  });

  it('never says the same thing twice, and always says the same thing for the same seed', () => {
    const again = speechTapes(createLifeRandom(21));
    expect(again).toEqual(tapes);
    const other = speechTapes(createLifeRandom(22));
    expect(opening(other).keys).not.toEqual(opening(tapes).keys);
  });
});

describe('on the rig', () => {
  it('is the speaking PATTERN, regenerated on every wrap — a long answer never loops', () => {
    expect(resolvePatterns('speaking').some(tape => tape.channel === 'mouthOpen')).toBe(true);
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'cozmo', family: 'calm' },
      lifeRandom: createLifeRandom(5),
    });
    rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    // Past the arrival, two chunks' worth of the longest chunk.
    trace(rig, 'mouthOpen', 60);
    const window = Math.round(SPEECH_CHUNK_MAX_MS / 16);
    const first = trace(rig, 'mouthOpen', window);
    const second = trace(rig, 'mouthOpen', window);
    expect(first).not.toEqual(second);
    // Both halves talk.
    expect(Math.max(...first)).toBeGreaterThan(0.3);
    expect(Math.max(...second)).toBeGreaterThan(0.3);
  });

  it('talks on a rig without entropy too, deterministically', () => {
    const a = createEyeRig({
      initial: { expression: 'speaking', styleId: 'cozmo', family: 'calm' },
    });
    const b = createEyeRig({
      initial: { expression: 'speaking', styleId: 'cozmo', family: 'calm' },
    });
    const ta = trace(a, 'mouthOpen', 400);
    const tb = trace(b, 'mouthOpen', 400);
    expect(ta).toEqual(tb);
    expect(Math.max(...ta)).toBeGreaterThan(0.3);
  });

  it('stops when the speech does: nothing of the chunk survives the next expression', () => {
    const rig = createEyeRig({
      initial: { expression: 'speaking', styleId: 'cozmo', family: 'calm' },
    });
    trace(rig, 'mouthOpen', 80);
    rig.setPose({ expression: 'neutral', styleId: 'cozmo', family: 'calm' });
    trace(rig, 'mouthOpen', 120);
    expect(rig.values().mouthOpen).toBeCloseTo(resolvePose('neutral', 'cozmo').mouthOpen, 2);
    expect(Math.abs(rig.values().mouthX)).toBeLessThan(0.005);
  });
});
