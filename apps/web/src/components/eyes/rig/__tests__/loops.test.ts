import { describe, it, expect } from 'vitest';
import { loopValue, waveValue, type LoopSpec } from '@/components/eyes/rig/loops';

describe('waveValue', () => {
  it('starts every waveform at zero, rising — so a phase means one thing', () => {
    (['sine', 'triangle', 'hold'] as const).forEach(waveform => {
      expect(waveValue(waveform, 0)).toBeCloseTo(0, 6);
      expect(waveValue(waveform, 0.01)).toBeGreaterThan(0);
    });
  });

  it('stays inside [-1, 1] over a full turn, for every waveform', () => {
    (['sine', 'triangle', 'hold'] as const).forEach(waveform => {
      for (let p = -1; p <= 2; p += 0.01) {
        const value = waveValue(waveform, p);
        expect(value).toBeGreaterThanOrEqual(-1.000001);
        expect(value).toBeLessThanOrEqual(1.000001);
      }
    });
  });

  it('peaks and troughs at the quarter turns', () => {
    (['sine', 'triangle', 'hold'] as const).forEach(waveform => {
      expect(waveValue(waveform, 0.25)).toBeCloseTo(1, 6);
      expect(waveValue(waveform, 0.75)).toBeCloseTo(-1, 6);
    });
  });

  it('dwells at the ends of travel for `hold`, unlike a sine', () => {
    // A scan holds at each extremity; a sine passes straight through.
    expect(waveValue('hold', 0.2)).toBe(1);
    expect(waveValue('sine', 0.2)).toBeLessThan(1);
  });

  it('is periodic', () => {
    (['sine', 'triangle', 'hold'] as const).forEach(waveform => {
      expect(waveValue(waveform, 0.37)).toBeCloseTo(waveValue(waveform, 1.37), 6);
      expect(waveValue(waveform, 0.37)).toBeCloseTo(waveValue(waveform, -0.63), 6);
    });
  });
});

describe('loopValue', () => {
  it('scales the waveform by the amplitude and reads the period', () => {
    const loop: LoopSpec = {
      channel: 'mass',
      amplitude: 0.02,
      periodMs: 1000,
      phase: 0,
      waveform: 'sine',
    };
    expect(loopValue(loop, 0)).toBeCloseTo(0, 9);
    expect(loopValue(loop, 250)).toBeCloseTo(0.02, 9);
    expect(loopValue(loop, 750)).toBeCloseTo(-0.02, 9);
  });
});
