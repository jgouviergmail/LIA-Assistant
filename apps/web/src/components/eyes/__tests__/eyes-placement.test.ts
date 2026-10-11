import { describe, expect, it } from 'vitest';
import { unobstructedPlacement } from '../eyes-placement';

const viewport = { width: 390, height: 800, minimumTop: 80 };
const size = { width: 120, height: 140 };
const preferred = { left: 246, top: 532 };

describe('default companion placement', () => {
  it('keeps its current place while the underlying actions remain free', () => {
    expect(unobstructedPlacement(preferred, size, viewport, [])).toEqual(preferred);
  });

  it('moves away from the actual controls without leaving the mobile viewport', () => {
    const obstacle = { left: 200, top: 500, right: 390, bottom: 700 };
    const point = unobstructedPlacement(preferred, size, viewport, [obstacle]);
    expect(point).not.toBeNull();
    if (!point) throw new Error('An unobstructed corner is available');
    expect(
      point.left + size.width <= obstacle.left || point.top + size.height <= obstacle.top
    ).toBe(true);
    expect(point.left).toBeGreaterThanOrEqual(8);
    expect(point.top).toBeGreaterThanOrEqual(viewport.minimumTop);
    expect(point.left + size.width).toBeLessThanOrEqual(viewport.width - 8);
    expect(point.top + size.height).toBeLessThanOrEqual(viewport.height - 8);
  });

  it('never chooses the occupied frame when every candidate is blocked', () => {
    expect(
      unobstructedPlacement(preferred, size, viewport, [
        { left: 0, top: 0, right: 390, bottom: 800 },
      ])
    ).toBeNull();
  });

  it('refuses a frame larger than its available viewport', () => {
    expect(unobstructedPlacement(preferred, size, { ...viewport, width: 100 }, [])).toBeNull();
  });
});
