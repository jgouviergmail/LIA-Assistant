/**
 * The text-size scale — bounds, validation of what storage or the API hands
 * back, and the TEXT scale factor the stylesheet multiplies every font size by.
 *
 * Only text follows the factor: panels, spacing and icons keep their size
 * whatever the reader picks (owner requirement 2026-09-29 — scaling the root
 * `rem` shrank the chat, the debug panel and the settings with the text).
 */

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_FONT_SIZE_PX,
  FONT_SIZE_MAX_PX,
  FONT_SIZE_MIN_PX,
  FONT_SIZE_STEPS,
  fontSizeScale,
  isValidFontSize,
  parseStoredFontSize,
} from '../fonts';

describe('font size bounds', () => {
  it('frames the default strictly inside the range', () => {
    expect(FONT_SIZE_MIN_PX).toBeLessThan(DEFAULT_FONT_SIZE_PX);
    expect(DEFAULT_FONT_SIZE_PX).toBeLessThan(FONT_SIZE_MAX_PX);
  });

  it('offers every whole pixel from the minimum to the maximum', () => {
    expect(FONT_SIZE_STEPS).toEqual([14, 15, 16, 17, 18, 19, 20]);
  });
});

describe('isValidFontSize', () => {
  it.each(FONT_SIZE_STEPS)('accepts %i', size => {
    expect(isValidFontSize(size)).toBe(true);
  });

  it.each([13, 21, 16.5, Number.NaN, Number.POSITIVE_INFINITY, '16', null, undefined])(
    'refuses %s',
    value => {
      expect(isValidFontSize(value)).toBe(false);
    }
  );
});

describe('parseStoredFontSize', () => {
  it('reads a stored step', () => {
    expect(parseStoredFontSize('18')).toBe(18);
  });

  // '018' too: the pre-paint script looks the raw value up verbatim, so the
  // provider must not read a spelling the script ignores.
  it.each([null, '', 'large', '13', '21', '16.5', '16px', ' 18', '018', '1e1'])(
    'refuses %j, which storage may hold after tampering or an old release',
    raw => {
      expect(parseStoredFontSize(raw)).toBeNull();
    }
  );
});

describe('fontSizeScale', () => {
  it.each([
    [14, 0.875],
    [16, 1],
    [18, 1.125],
    [20, 1.25],
  ])('%i px multiplies every text size by %f', (px, scale) => {
    expect(fontSizeScale(px)).toBe(scale);
  });
});
