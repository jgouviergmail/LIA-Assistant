/**
 * Speech — generated, never looped.
 *
 * A talking mouth used to be a sum of sines on the opening: it got louder and
 * quieter, it closed on a slow envelope, and over a long answer it said the
 * same phrase again and again. This module writes SPEECH the way an animator
 * would key it: syllables (an open, a close, six or so a second, no two the
 * same size), words of one to five syllables, short gaps
 * between words and long ones between phrases, a SHAPE per word (width,
 * curve, corners, a sideways slide), and a stressed word now and then that
 * the brows mark — both, or one alone — with the head nodding on some.
 *
 * The output is a CHUNK: one set of relative tapes that all share one length
 * and end on a pause, so the rig can play it as the speaking pattern and
 * regenerate it when it wraps — the next chunk is another chunk, never the
 * same one. Pure given its entropy: the same seed talks the same way.
 */

import type { ChannelKey } from '@/components/eyes/rig/channels';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { Tape, TapeKey } from '@/components/eyes/rig/tape';

/** What the generator wants a chunk to last — it ends on the first pause
 * past the target, so the real length runs a little over. */
const SPEECH_TARGET_MIN_MS = 5500;
const SPEECH_TARGET_MAX_MS = 8000;
/** Bounds on the actual chunk: the target plus at most one word and one
 * phrase pause. */
export const SPEECH_CHUNK_MIN_MS = SPEECH_TARGET_MIN_MS;
export const SPEECH_CHUNK_MAX_MS = 10_000;

/** A syllable: how far the mouth parts, and for how long, then the close. */
export const SPEECH_OPEN_MIN = 0.22;
export const SPEECH_OPEN_MAX = 0.66;
const SYLLABLE_OPEN_MIN_MS = 60;
const SYLLABLE_OPEN_MAX_MS = 130;
const SYLLABLE_CLOSE_MIN_MS = 45;
const SYLLABLE_CLOSE_MAX_MS = 95;
/** The close between two syllables of one word is not quite shut. */
const SYLLABLE_CLOSE_MAX = 0.08;

/** Words: one to five syllables, the short ones common. */
const SYLLABLES_PER_WORD: readonly (readonly [number, number])[] = [
  [1, 0.2],
  [2, 0.35],
  [3, 0.25],
  [4, 0.13],
  [5, 0.07],
];

/** Gaps: between two words, and between two phrases (every 4 to 9 words). */
export const SPEECH_WORD_GAP_MIN_MS = 120;
const SPEECH_WORD_GAP_MAX_MS = 300;
export const SPEECH_PHRASE_GAP_MIN_MS = 550;
const SPEECH_PHRASE_GAP_MAX_MS = 1000;
const PHRASE_WORDS_MIN = 4;
const PHRASE_WORDS_MAX = 9;

/** The shape of a word, as offsets from the speaking pose. */
const WORD_WIDTH = [-0.14, 0.18] as const;
const WORD_CURVE = [-0.08, 0.16] as const;
const WORD_SKEW = [-0.14, 0.14] as const;
const WORD_SLIDE_EM = [-0.025, 0.025] as const;

/** Stress: a share of the words, marked by the brows; a share of those by
 * one brow only, and by a nod of the head. */
const STRESS_PROBABILITY = 0.35;
const ONE_BROW_PROBABILITY = 0.3;
const NOD_PROBABILITY = 0.5;
const STRESS_LIFT_EM = [-0.03, -0.055] as const;
const STRESS_ARCH = [0.15, 0.28] as const;
const NOD_EM = -0.01;
/** The right brow trails and moves a hair less, as everywhere on the face. */
const RIGHT_TRAIL_MS = 40;
const RIGHT_SCALE = 0.92;

/** Springs: the flap is quick, the shape follows, the brows punctuate. */
const FLAP: SpringConfig = { frequency: 7, damping: 0.85 };
const SHAPE: SpringConfig = { frequency: 3.2, damping: 0.8 };
const STRESS: SpringConfig = { frequency: 3.4, damping: 0.6 };
const NOD: SpringConfig = { frequency: 2.5, damping: 0.7 };

/** The channels speech is allowed to own — and nothing else. */
export const SPEECH_CHANNELS: ReadonlySet<ChannelKey> = new Set<ChannelKey>([
  'mouthOpen',
  'mouthW',
  'mouthCurve',
  'mouthSkew',
  'mouthX',
  'browYL',
  'browYR',
  'browArcL',
  'browArcR',
  'massY',
]);

type Random = () => number;

function between(random: Random, [min, max]: readonly [number, number]): number {
  return min + random() * (max - min);
}

function betweenMs(random: Random, min: number, max: number): number {
  return Math.round(min + random() * (max - min));
}

function drawSyllables(random: Random): number {
  let cursor = random();
  for (const [count, weight] of SYLLABLES_PER_WORD) {
    cursor -= weight;
    if (cursor < 0) return count;
  }
  return 1;
}

/** Keys are pushed as `[atMs, value]` pairs per channel, then wrapped. */
type KeyLog = Map<ChannelKey, TapeKey[]>;

function key(log: KeyLog, channel: ChannelKey, atMs: number, value: number): void {
  const keys = log.get(channel) ?? [];
  keys.push({ atMs, value: value + 0 });
  log.set(channel, keys);
}

/** One word: its syllables on the opening, its shape, and its stress. Returns
 * the time at which the word ends (the mouth shut). */
function word(log: KeyLog, random: Random, startMs: number): number {
  // The shape of the word lands with its first syllable.
  key(log, 'mouthW', startMs, between(random, WORD_WIDTH));
  key(log, 'mouthCurve', startMs, between(random, WORD_CURVE));
  key(log, 'mouthSkew', startMs, between(random, WORD_SKEW));
  key(log, 'mouthX', startMs, between(random, WORD_SLIDE_EM));
  let t = startMs;
  const syllables = drawSyllables(random);
  for (let index = 0; index < syllables; index += 1) {
    key(log, 'mouthOpen', t, between(random, [SPEECH_OPEN_MIN, SPEECH_OPEN_MAX]));
    t += betweenMs(random, SYLLABLE_OPEN_MIN_MS, SYLLABLE_OPEN_MAX_MS);
    const last = index === syllables - 1;
    key(log, 'mouthOpen', t, last ? 0 : random() * SYLLABLE_CLOSE_MAX);
    t += betweenMs(random, SYLLABLE_CLOSE_MIN_MS, SYLLABLE_CLOSE_MAX_MS);
  }
  if (random() < STRESS_PROBABILITY) stress(log, random, startMs, t);
  return t;
}

/** A stressed word: the brows lift and arch for its length — both, the
 * right one trailing and smaller, or the left one alone — and the head may
 * nod with it. */
function stress(log: KeyLog, random: Random, fromMs: number, toMs: number): void {
  const lift = between(random, STRESS_LIFT_EM);
  const arch = between(random, STRESS_ARCH);
  key(log, 'browYL', fromMs, lift);
  key(log, 'browArcL', fromMs, arch);
  key(log, 'browYL', toMs, 0);
  key(log, 'browArcL', toMs, 0);
  if (random() >= ONE_BROW_PROBABILITY) {
    key(log, 'browYR', fromMs + RIGHT_TRAIL_MS, lift * RIGHT_SCALE);
    key(log, 'browArcR', fromMs + RIGHT_TRAIL_MS, arch * RIGHT_SCALE);
    key(log, 'browYR', toMs + RIGHT_TRAIL_MS, 0);
    key(log, 'browArcR', toMs + RIGHT_TRAIL_MS, 0);
  }
  if (random() < NOD_PROBABILITY) {
    key(log, 'massY', fromMs, NOD_EM);
    key(log, 'massY', toMs, 0);
  }
}

const SPRING_FOR: Record<string, SpringConfig> = {
  mouthOpen: FLAP,
  mouthW: SHAPE,
  mouthCurve: SHAPE,
  mouthSkew: SHAPE,
  mouthX: SHAPE,
  browYL: STRESS,
  browYR: STRESS,
  browArcL: STRESS,
  browArcR: STRESS,
  massY: NOD,
};

/**
 * One chunk of speech: a set of relative tapes of one shared length, ending
 * on a pause. Every channel speech touches gets a tape — a channel with
 * nothing to say gets a single resting key, so the set is stable and the
 * rig's regeneration on wrap never changes which channels are held.
 */
export function speechTapes(random: Random): Tape[] {
  const log: KeyLog = new Map();
  const targetMs = betweenMs(random, SPEECH_TARGET_MIN_MS, SPEECH_TARGET_MAX_MS);
  let t = 0;
  let words = 0;
  let nextBreak = betweenMs(random, PHRASE_WORDS_MIN, PHRASE_WORDS_MAX);
  while (t < targetMs) {
    t = word(log, random, t);
    words += 1;
    if (words >= nextBreak) {
      // A phrase ends: the mouth relaxes to the pose while it pauses.
      key(log, 'mouthW', t, 0);
      key(log, 'mouthCurve', t, 0);
      key(log, 'mouthSkew', t, 0);
      key(log, 'mouthX', t, 0);
      t += betweenMs(random, SPEECH_PHRASE_GAP_MIN_MS, SPEECH_PHRASE_GAP_MAX_MS);
      nextBreak = words + betweenMs(random, PHRASE_WORDS_MIN, PHRASE_WORDS_MAX);
    } else {
      t += betweenMs(random, SPEECH_WORD_GAP_MIN_MS, SPEECH_WORD_GAP_MAX_MS);
    }
  }
  const chunkMs = t;
  return [...SPEECH_CHANNELS].map(channel => ({
    channel,
    keys: log.get(channel) ?? [{ atMs: 0, value: 0 }],
    durationMs: chunkMs,
    spring: SPRING_FOR[channel],
    relative: true,
  }));
}
