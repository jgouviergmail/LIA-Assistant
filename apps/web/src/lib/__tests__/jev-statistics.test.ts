/**
 * What a JEV threshold concludes, read from the buckets alone (ADR-374).
 *
 * The backend files a confidence at floor(score × 100) and a margin's judgement at its
 * distance to certainty, ceil(min(p, 1 − p) × 100) (`jev_gates.judgement_bucket`). A
 * confidence then concludes from bucket t × 100 up, a margin up to bucket m × 100 —
 * exactly, which `test_a_bucket_concludes_exactly_when_its_score_passes` proves on the
 * server. These are the screen's twin of that rule.
 */
import { describe, expect, it } from 'vitest';
import { bucketConcludes, concludedShare, thresholdBands } from '@/lib/jev-statistics';

function buckets(entries: Record<number, number>): number[] {
  const list = new Array<number>(101).fill(0);
  for (const [bucket, count] of Object.entries(entries)) list[Number(bucket)] = count;
  return list;
}

describe('bucketConcludes', () => {
  it('concludes a confidence from its threshold up, inclusively', () => {
    expect(bucketConcludes('choice_concentration', 80, 0.8)).toBe(true);
    expect(bucketConcludes('choice_concentration', 79, 0.8)).toBe(false);
    expect(bucketConcludes('choice_confidence', 100, 1)).toBe(true);
  });

  it('concludes a margin up to its threshold, inclusively', () => {
    expect(bucketConcludes('margin', 16, 0.16)).toBe(true);
    expect(bucketConcludes('margin', 17, 0.16)).toBe(false);
    expect(bucketConcludes('margin', 0, 0.02)).toBe(true);
  });

  it('reads a threshold at the hundredth whatever its floating-point spelling', () => {
    // 0.29 * 100 is 28.999999999999996 in floating point.
    expect(bucketConcludes('choice_confidence', 29, 0.29)).toBe(true);
    expect(bucketConcludes('margin', 29, 0.29)).toBe(true);
  });
});

describe('concludedShare', () => {
  it('counts what concludes at the threshold over every judgement', () => {
    const counts = buckets({ 50: 1, 79: 2, 80: 3, 100: 4 });
    expect(concludedShare('choice_confidence', counts, 0.8)).toEqual({ concluded: 7, total: 10 });
    expect(concludedShare('choice_confidence', counts, 0.81)).toEqual({ concluded: 4, total: 10 });
  });

  it('counts a margin from certainty outward', () => {
    const counts = buckets({ 0: 5, 16: 1, 17: 2, 50: 2 });
    expect(concludedShare('margin', counts, 0.16)).toEqual({ concluded: 6, total: 10 });
  });

  it('says nothing concluded when nothing was judged', () => {
    expect(concludedShare('choice_confidence', buckets({}), 0.8)).toEqual({
      concluded: 0,
      total: 0,
    });
  });
});

describe('thresholdBands', () => {
  it('folds a confidence into ten bands, most confident first, split at the threshold', () => {
    const bands = thresholdBands(
      'choice_confidence',
      buckets({ 100: 1, 85: 2, 84: 3, 3: 4 }),
      0.85
    );
    expect(bands).toHaveLength(10);
    expect(bands[0]).toEqual({ from: 0.9, to: 1, concludes: 1, handsBack: 0 });
    expect(bands[1]).toEqual({ from: 0.8, to: 0.89, concludes: 2, handsBack: 3 });
    expect(bands[9]).toEqual({ from: 0, to: 0.09, concludes: 0, handsBack: 4 });
    expect(bands.reduce((sum, band) => sum + band.concludes + band.handsBack, 0)).toBe(10);
  });

  it('folds a margin into ten bands of distance, closest to certainty first', () => {
    const bands = thresholdBands('margin', buckets({ 0: 1, 16: 2, 17: 3, 50: 4 }), 0.16);
    expect(bands).toHaveLength(10);
    expect(bands[0]).toEqual({ from: 0, to: 0.04, concludes: 1, handsBack: 0 });
    expect(bands[3]).toEqual({ from: 0.15, to: 0.19, concludes: 2, handsBack: 3 });
    expect(bands[9]).toEqual({ from: 0.45, to: 0.5, concludes: 0, handsBack: 4 });
  });
});
