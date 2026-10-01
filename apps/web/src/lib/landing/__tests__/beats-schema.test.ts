/**
 * The beat map is the operator's file too (ADR-330): what reaches the page is
 * a bounded, ordered list of `[ms, weight, bar]` triples, or nothing.
 */

import { describe, expect, it } from 'vitest';

import { BEAT_MAP_MAX_ENTRIES, parseBeatMap } from '../beats-schema';

const MAP = {
  version: 1,
  beats: [
    [0, 1, true],
    [464, 0.6, false],
    [929, 0.7, false],
    [1393, 0.55, false],
    [1858, 1, true],
  ],
};

describe('parseBeatMap', () => {
  it('accepts an ordered map and keeps its triples', () => {
    expect(parseBeatMap(MAP)).toEqual(MAP);
  });

  it('refuses beats out of order, a weight past 1, a negative instant, a wrong version', () => {
    expect(() =>
      parseBeatMap({
        version: 1,
        beats: [
          [500, 1, true],
          [400, 1, false],
        ],
      })
    ).toThrow();
    expect(() => parseBeatMap({ version: 1, beats: [[0, 1.5, true]] })).toThrow();
    expect(() => parseBeatMap({ version: 1, beats: [[-1, 1, true]] })).toThrow();
    expect(() => parseBeatMap({ version: 2, beats: [[0, 1, true]] })).toThrow();
    expect(() => parseBeatMap('nope')).toThrow();
  });

  it('is bounded', () => {
    const beats = Array.from({ length: BEAT_MAP_MAX_ENTRIES + 1 }, (_, i) => [i * 10, 0.5, false]);
    expect(() => parseBeatMap({ version: 1, beats })).toThrow();
    expect(
      parseBeatMap({ version: 1, beats: beats.slice(0, BEAT_MAP_MAX_ENTRIES) }).beats
    ).toHaveLength(BEAT_MAP_MAX_ENTRIES);
  });

  it('accepts an empty map (a silent track) rather than failing the section', () => {
    expect(parseBeatMap({ version: 1, beats: [] }).beats).toEqual([]);
  });
});
