/**
 * The forgotten-stop guard: prompts once after continuous silence, never
 * while someone speaks, and re-arms after "continue".
 */

import { describe, expect, it } from 'vitest';

import { SilenceWatchdog } from '../silence-watchdog';

const MINUTE = 60_000;

describe('SilenceWatchdog', () => {
  it('reports speech and never prompts while the level stays above the threshold', () => {
    const dog = new SilenceWatchdog({ thresholdRms: 0.01, promptAfterMs: 10 * MINUTE });
    for (let i = 0; i < 100; i++) {
      expect(dog.feed(0.2, i * MINUTE)).toBe('speech');
    }
  });

  it('prompts exactly once after the silent stretch and stays silent afterwards', () => {
    const dog = new SilenceWatchdog({ thresholdRms: 0.01, promptAfterMs: 10 * MINUTE });
    expect(dog.feed(0.0, 0)).toBe('silence');
    expect(dog.feed(0.0, 9 * MINUTE)).toBe('silence');
    expect(dog.feed(0.0, 10 * MINUTE)).toBe('prompt');
    expect(dog.feed(0.0, 11 * MINUTE)).toBe('silence');
    expect(dog.feed(0.0, 30 * MINUTE)).toBe('silence');
  });

  it('measures the stretch from the FIRST silent reading, not from the last speech', () => {
    const dog = new SilenceWatchdog({ thresholdRms: 0.01, promptAfterMs: 10 * MINUTE });
    dog.feed(0.5, 0);
    dog.feed(0.0, 5 * MINUTE);
    expect(dog.feed(0.0, 14 * MINUTE)).toBe('silence');
    expect(dog.feed(0.0, 15 * MINUTE)).toBe('prompt');
    expect(dog.silentFor(15 * MINUTE)).toBe(10 * MINUTE);
  });

  it('speech resets the stretch so the prompt can fire again later', () => {
    const dog = new SilenceWatchdog({ thresholdRms: 0.01, promptAfterMs: 10 * MINUTE });
    expect(dog.feed(0.0, 10 * MINUTE)).toBe('silence');
    expect(dog.feed(0.0, 20 * MINUTE)).toBe('prompt');
    expect(dog.feed(0.3, 21 * MINUTE)).toBe('speech');
    expect(dog.silentFor(21 * MINUTE)).toBe(0);
    expect(dog.feed(0.0, 22 * MINUTE)).toBe('silence');
    expect(dog.feed(0.0, 32 * MINUTE)).toBe('prompt');
  });

  it('"continue" re-arms a fresh window from the acknowledgement', () => {
    const dog = new SilenceWatchdog({ thresholdRms: 0.01, promptAfterMs: 10 * MINUTE });
    dog.feed(0.0, 0);
    expect(dog.feed(0.0, 10 * MINUTE)).toBe('prompt');
    dog.acknowledge(10 * MINUTE);
    expect(dog.feed(0.0, 19 * MINUTE)).toBe('silence');
    expect(dog.feed(0.0, 20 * MINUTE)).toBe('prompt');
  });
});
