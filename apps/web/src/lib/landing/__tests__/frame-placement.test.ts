/**
 * The framed player is placed in DOCUMENT coordinates (ADR-330 amendment): the
 * slot's rect plus the scroll offsets, rounded to the pixel, so the player
 * scrolls with the page natively instead of chasing it.
 */

import { describe, expect, it } from 'vitest';

import { placementFor } from '../frame-placement';

describe('placementFor', () => {
  it('adds the scroll offsets to the viewport rect and rounds to the pixel', () => {
    expect(placementFor({ top: 10.4, left: 20.6, width: 300.2, height: 168.9 }, 5, 1000)).toEqual({
      top: 1010,
      left: 26,
      width: 300,
      height: 169,
    });
  });

  it('keeps a slot above the fold where it is', () => {
    expect(placementFor({ top: 0, left: 0, width: 640, height: 360 }, 0, 0)).toEqual({
      top: 0,
      left: 0,
      width: 640,
      height: 360,
    });
  });
});
