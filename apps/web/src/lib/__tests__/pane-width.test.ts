/**
 * The one rule every hand-sized pane obeys: a width inside its bounds, in whole pixels.
 */

import { describe, expect, it } from 'vitest';

import { clampPaneWidth } from '../pane-width';

describe('clampPaneWidth', () => {
  const bounds = { min: 320, max: 900 };

  it('keeps a width inside the bounds, in whole pixels', () => {
    expect(clampPaneWidth(512.6, bounds)).toBe(513);
  });

  it('stops at either bound', () => {
    expect(clampPaneWidth(100, bounds)).toBe(320);
    expect(clampPaneWidth(5000, bounds)).toBe(900);
  });
});
