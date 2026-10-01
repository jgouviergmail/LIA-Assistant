import { describe, expect, it } from 'vitest';

import { DetectionPolicy } from '../policy';

/** Feed one score per chunk, chunk numbers starting at 1; return the chunks that fired. */
function fired(policy: DetectionPolicy, scores: number[]): number[] {
  const out: number[] = [];
  scores.forEach((score, index) => {
    if (policy.push(score)) out.push(index + 1);
  });
  return out;
}

const WARMUP = 25;
const quiet = (n: number) => Array.from({ length: n }, () => 0);

describe('DetectionPolicy', () => {
  it('never fires during the warm-up, whatever the score', () => {
    const policy = new DetectionPolicy({
      threshold: 0.5,
      patience: 1,
      refractoryChunks: 25,
      warmupChunks: WARMUP,
    });
    expect(
      fired(
        policy,
        Array.from({ length: WARMUP - 1 }, () => 1)
      )
    ).toEqual([]);
  });

  it('fires on the first chunk at or above the threshold once warm', () => {
    const policy = new DetectionPolicy({
      threshold: 0.5,
      patience: 1,
      refractoryChunks: 25,
      warmupChunks: WARMUP,
    });
    expect(fired(policy, [...quiet(WARMUP), 0.49, 0.5])).toEqual([WARMUP + 2]);
  });

  it('a run that started in the warm-up does not count towards the patience', () => {
    const policy = new DetectionPolicy({
      threshold: 0.5,
      patience: 2,
      refractoryChunks: 25,
      warmupChunks: WARMUP,
    });
    // chunks 24 (warm-up) and 25 are high: only chunk 25 counts, so no detection
    // until chunk 26 completes a run of two warm chunks.
    const scores = [...quiet(WARMUP - 2), 0.9, 0.9, 0.9];
    expect(fired(policy, scores)).toEqual([WARMUP + 1]);
  });

  it('needs `patience` consecutive chunks above the threshold', () => {
    const policy = new DetectionPolicy({
      threshold: 0.5,
      patience: 3,
      refractoryChunks: 25,
      warmupChunks: WARMUP,
    });
    const scores = [...quiet(WARMUP), 0.9, 0.9, 0.1, 0.9, 0.9, 0.9];
    expect(fired(policy, scores)).toEqual([WARMUP + 6]);
  });

  it('stays silent for the refractory period after a detection, then can fire again', () => {
    const policy = new DetectionPolicy({
      threshold: 0.5,
      patience: 1,
      refractoryChunks: 3,
      warmupChunks: WARMUP,
    });
    const scores = [...quiet(WARMUP), 0.9, 0.9, 0.9, 0.9, 0.9];
    // fires at chunk 26, silent for 27-29, fires again at 30
    expect(fired(policy, scores)).toEqual([WARMUP + 1, WARMUP + 5]);
  });

  it('agrees with the toolbox rule (scripts/wake-word Policy.detections) on random streams', () => {
    // The toolbox's formulation, transcribed: mask the warm-up, a sliding window
    // of `patience` chunks all above, then a greedy refractory over the
    // candidates. Independent of the chunk-by-chunk state machine under test.
    const toolbox = (scores: number[], p: number, r: number, w: number, t: number) => {
      const above = scores.map((s, i) => i >= w - 1 && s >= t);
      const candidates = above.flatMap((_, i) =>
        i >= p - 1 && above.slice(i - p + 1, i + 1).every(Boolean) ? [i] : []
      );
      const out: number[] = [];
      let last = -(r + 1);
      for (const i of candidates) {
        if (i - last > r) {
          out.push(i + 1);
          last = i;
        }
      }
      return out;
    };
    let seed = 7;
    const random = () => {
      seed = (seed * 1103515245 + 12345) % 2 ** 31;
      return seed / 2 ** 31;
    };
    for (let trial = 0; trial < 400; trial += 1) {
      const patience = 1 + (trial % 4);
      const refractory = trial % 6;
      const warmup = 1 + (trial % 5);
      const scores = Array.from({ length: 60 }, () => (random() < 0.6 ? 0.9 : 0.1));
      const policy = new DetectionPolicy({
        threshold: 0.5,
        patience,
        refractoryChunks: refractory,
        warmupChunks: warmup,
      });
      expect(fired(policy, scores), `trial ${trial}`).toEqual(
        toolbox(scores, patience, refractory, warmup, 0.5)
      );
    }
  });

  it('reset() restarts the warm-up and forgets the refractory period', () => {
    const policy = new DetectionPolicy({
      threshold: 0.5,
      patience: 1,
      refractoryChunks: 25,
      warmupChunks: WARMUP,
    });
    fired(policy, [...quiet(WARMUP), 0.9]);
    policy.reset();
    // chunk 24 (still warming up) scores high: nothing; chunk 25 fires
    expect(fired(policy, [...quiet(WARMUP - 2), 0.9])).toEqual([]);
    expect(policy.push(0.9)).toBe(true);
  });
});
