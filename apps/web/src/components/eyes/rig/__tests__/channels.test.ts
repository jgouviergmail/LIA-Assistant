/**
 * Channel table — the rig's vocabulary and its contract with the stylesheet.
 *
 * The boundary rule of the whole system ("TS owns what MOVES, CSS owns what is
 * DRAWN") is only enforceable because every animated property is a `--rig-*`
 * custom property declared here. These tests pin that invariant, the L/R
 * symmetry (an asymmetry must be a POSE decision, never a table typo) and the
 * serialization, whose precision doubles as the "has it changed?" threshold.
 */

import { describe, it, expect } from 'vitest';
import {
  CHANNELS,
  CHANNEL_KEYS,
  EYE_CHANNEL_BASES,
  formatChannel,
  restChannelValues,
  type ChannelKey,
} from '@/components/eyes/rig/channels';

describe('channel table', () => {
  it('exposes every declared channel in a stable ordered list', () => {
    expect(CHANNEL_KEYS).toHaveLength(Object.keys(CHANNELS).length);
    expect(new Set(CHANNEL_KEYS).size).toBe(CHANNEL_KEYS.length);
  });

  it('drives ONLY `--rig-*` custom properties, each one unique', () => {
    const vars = CHANNEL_KEYS.map(key => CHANNELS[key].cssVar);
    vars.forEach(cssVar => expect(cssVar).toMatch(/^--rig-[a-z0-9-]+$/));
    expect(new Set(vars).size).toBe(vars.length);
  });

  it('declares finite rest values and a positive precision everywhere', () => {
    CHANNEL_KEYS.forEach(key => {
      const def = CHANNELS[key];
      expect(Number.isFinite(def.rest)).toBe(true);
      expect(def.precision).toBeGreaterThanOrEqual(0);
    });
  });

  it('mirrors every per-eye channel into an L/R pair with identical physics', () => {
    EYE_CHANNEL_BASES.forEach(base => {
      const left = CHANNELS[`${base}L` as ChannelKey];
      const right = CHANNELS[`${base}R` as ChannelKey];
      expect(left).toBeDefined();
      expect(right).toBeDefined();
      expect(left.rest).toBe(right.rest);
      expect(left.group).toBe(right.group);
      expect(left.unit).toBe(right.unit);
      expect(left.snap).toBe(right.snap);
      expect(left.derived).toBe(right.derived);
      expect(left.cssVar).toBe(`${right.cssVar.slice(0, -2)}-l`);
    });
  });

  it('builds a rest snapshot covering every channel', () => {
    const rest = restChannelValues();
    expect(Object.keys(rest)).toHaveLength(CHANNEL_KEYS.length);
    CHANNEL_KEYS.forEach(key => expect(rest[key]).toBe(CHANNELS[key].rest));
  });
});

describe('formatChannel', () => {
  it('serializes each unit with its CSS suffix', () => {
    expect(formatChannel('syL', 0.5)).toBe('0.5');
    expect(formatChannel('tyL', -0.0812)).toBe('-0.081em');
    expect(formatChannel('rotL', 7.129)).toBe('7.13deg');
    expect(formatChannel('lidTopL', 46.27)).toBe('46.3%');
  });

  it('rounds to the channel precision — the change threshold of the loop', () => {
    expect(formatChannel('tyL', 0.0001)).toBe('0em');
    expect(formatChannel('tyL', 0.0006)).toBe('0.001em');
  });

  it('never emits a negative zero (it would churn the style attribute)', () => {
    expect(formatChannel('tyL', -0.00001)).toBe('0em');
    expect(formatChannel('gazeX', -0.00001)).toBe('0');
  });
});
