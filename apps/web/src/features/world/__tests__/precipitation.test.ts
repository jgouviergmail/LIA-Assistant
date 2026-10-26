import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { expect, it, vi } from 'vitest';
import { paintPrecipitation } from '../art/precipitation';
import { createCamera } from '../geometry';
import { WORLD } from '../definition';
import type { Quality } from '../types';

function context() {
  let depth = 0;
  const states: number[] = [];
  const points: number[][] = [];
  const c = canvasContext({
    globalAlpha: 0.7,
    save: () => {
      depth++;
      states.push(c.globalAlpha);
    },
    restore: () => {
      depth--;
      c.globalAlpha = states.pop()!;
    },
    beginPath: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    moveTo: (...n: number[]) => points.push(n),
    lineTo: (...n: number[]) => points.push(n),
    ellipse: (x, y, rx, ry, rotation, start, end) => {
      points.push([x, y, rx, ry, rotation, start, end]);
    },
    arc: (x, y, radius, start, end) => {
      points.push([x, y, radius, start, end]);
    },
  });
  return { c: c, points, depth: () => depth };
}
it.each<Quality>(['low', 'balanced', 'high'])(
  'keeps %s precipitation finite, bounded and restores shared canvas state',
  quality => {
    for (const rain of [false, true]) {
      const camera = createCamera({ width: 568, height: 320 }, { x: 25, y: 25 });
      for (const zoom of [0.55, 1.8]) {
        camera.zoom = zoom;
        for (const time of [0, 1.2, 3600, 86400]) {
          const { c, points, depth } = context();
          paintPrecipitation(c, { ...WORLD, zones: [] }, camera, time, quality, rain);
          expect(points.length).toBeGreaterThan(0);
          expect(points.length).toBeLessThan(1000);
          expect(points.flat().every(Number.isFinite)).toBe(true);
          expect(depth()).toBe(0);
          expect(c.globalAlpha).toBe(0.7);
        }
      }
    }
  }
);
it('does not emit rain, snow or impacts anywhere inside a covered camera footprint', () => {
  const camera = createCamera({ width: 320, height: 240 }, { x: 25, y: 25 });
  const world = {
    ...WORLD,
    zones: [{ ...WORLD.zones[0], x: 0, y: 0, width: 60, height: 60, covered: true }],
  };
  for (const rain of [false, true]) {
    const { c, points, depth } = context();
    paintPrecipitation(c, world, camera, 3.6, 'high', rain);
    expect(points).toEqual([]);
    expect(depth()).toBe(0);
  }
});
