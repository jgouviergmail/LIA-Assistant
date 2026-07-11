/**
 * MOOD_COLORS codepoint invariants + animated-asset completeness guard
 * (frontend analog of the backend registry-completeness asserts, ADR-085 spirit).
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import { MOOD_COLORS, getMoodColor } from '../psyche-colors';

const ASSETS_DIR = join(__dirname, '..', '..', '..', 'public', 'animated-emoji');

describe('MOOD_COLORS codepoints', () => {
  it('every mood has a well-formed, unique codepoint', () => {
    const codepoints = Object.values(MOOD_COLORS).map(c => c.codepoint);
    for (const cp of codepoints) {
      expect(cp).toMatch(/^[0-9a-f]{4,5}(-[0-9a-f]{4,5})*$/);
    }
    expect(new Set(codepoints).size).toBe(codepoints.length);
  });

  it('codepoint is derived from the Unicode fallback glyph', () => {
    for (const config of Object.values(MOOD_COLORS)) {
      const derived = [...config.icon]
        .map(ch => (ch.codePointAt(0) as number).toString(16))
        .join('-');
      expect(config.codepoint).toBe(derived);
    }
  });

  it('has a self-hosted animated asset for every mood (registry completeness)', () => {
    for (const [mood, config] of Object.entries(MOOD_COLORS)) {
      expect(
        existsSync(join(ASSETS_DIR, `${config.codepoint}.webp`)),
        `missing animated asset for mood "${mood}" (${config.codepoint}.webp)`
      ).toBe(true);
    }
  });

  it('falls back to neutral for unknown labels', () => {
    expect(getMoodColor('nope')).toBe(MOOD_COLORS.neutral);
  });
});
