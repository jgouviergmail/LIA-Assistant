import { describe, expect, it } from 'vitest';
import { fitActorLabel } from '../art/labels';

describe('readable international nameplates', () => {
  const measure = (value: string) => Array.from(value).length * 10;
  it('keeps short names intact and bounds long names inside the actor surface', () => {
    expect(fitActorLabel('LIA', measure, 100)).toBe('LIA');
    const long = fitActorLabel('Character name too long', measure, 100);
    expect(long.endsWith('…')).toBe(true);
    expect(measure(long)).toBeLessThanOrEqual(100);
  });
  it('never splits an emoji or a combining grapheme and handles an unavailable width', () => {
    expect(fitActorLabel('🌿'.repeat(24), measure, 40)).toBe('🌿🌿🌿…');
    expect(fitActorLabel('e\u0301'.repeat(24), measure, 50)).toBe('e\u0301e\u0301…');
    expect(fitActorLabel('A', measure, 1)).toBe('');
  });
});
