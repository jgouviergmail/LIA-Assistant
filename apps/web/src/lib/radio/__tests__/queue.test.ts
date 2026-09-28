/**
 * The player's queue: ascending, deduplicated, skipping what the server never delivered.
 */
import { describe, expect, it } from 'vitest';

import { lineAt, mergeSegments, nextSegment } from '../queue';
import type { RadioSegment, RadioTranscriptLine } from '../types';

function segment(seq: number, title = `S${seq}`): RadioSegment {
  return { seq, format: 'brief', mood: 'news', title, duration_s: 40, transcript: [] };
}

describe('mergeSegments', () => {
  it('keeps one segment per place, ascending, the newest report winning', () => {
    const merged = mergeSegments([segment(3), segment(2)], [segment(3, 'again'), segment(4)], 1);
    expect(merged.map(s => [s.seq, s.title])).toEqual([
      [2, 'S2'],
      [3, 'again'],
      [4, 'S4'],
    ]);
  });

  it('drops what has already aired', () => {
    expect(mergeSegments([], [segment(1), segment(2)], 1).map(s => s.seq)).toEqual([2]);
  });
});

describe('nextSegment', () => {
  it('skips a place the server never delivered', () => {
    expect(nextSegment([segment(4), segment(6)], 3)?.seq).toBe(4);
    expect(nextSegment([segment(6)], 4)?.seq).toBe(6);
    expect(nextSegment([segment(2)], 2)).toBeNull();
  });
});

describe('lineAt', () => {
  const line = (offset_s: number): RadioTranscriptLine => ({
    role: 'anchor',
    text: `at ${offset_s}`,
    offset_s,
    sources: [],
  });
  const lines = [line(1.2), line(4.7), line(9.8)];

  it('follows the voice through the segment', () => {
    expect(lineAt(lines, 0.5)).toBe(-1);
    expect(lineAt(lines, 1.2)).toBe(0);
    expect(lineAt(lines, 6)).toBe(1);
    expect(lineAt(lines, 30)).toBe(2);
  });
});
