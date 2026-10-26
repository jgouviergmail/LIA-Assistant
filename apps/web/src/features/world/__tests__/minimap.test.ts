import { describe, expect, it } from 'vitest';
import { mapPoint } from '../minimap-geometry';
import { WORLD } from '../definition';

describe('map orientation', () => {
  it('maps each visible zone marker back to its world location', () => {
    const span = WORLD.width + WORLD.height;
    for (const zone of WORLD.zones) {
      const { x, y } = zone.arrival;
      const point = mapPoint(
        { x: (x - y + WORLD.height + 4) / (span + 8), y: ((x + y) / 2 + 4) / (span / 2 + 8) },
        WORLD
      );
      expect(point.x).toBeCloseTo(x);
      expect(point.y).toBeCloseTo(y);
    }
  });
  it('keeps clicks on the border inside the navigable map', () => {
    for (const x of [0, 1])
      for (const y of [0, 1]) {
        const point = mapPoint({ x, y }, WORLD);
        expect(point.x).toBeGreaterThanOrEqual(0);
        expect(point.y).toBeGreaterThanOrEqual(0);
        expect(point.x).toBeLessThanOrEqual(WORLD.width);
        expect(point.y).toBeLessThanOrEqual(WORLD.height);
      }
  });
});
