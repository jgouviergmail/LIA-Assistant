import { expect, it } from 'vitest';
import { coveredRectangles, isSheltered } from '../shelter';
import { WORLD } from '../definition';
it('unions nested and adjoining interior bounds so night masks never darken overlap areas', () => {
  const rects = coveredRectangles(WORLD);
  for (let i = 0; i < rects.length; i++)
    for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i],
        b = rects[j];
      expect(
        a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y
      ).toBe(false);
    }
  for (let y = 0; y < WORLD.height; y++)
    for (let x = 0; x < WORLD.width; x++) {
      const p = { x: x + 0.5, y: y + 0.5 };
      const contains = rects.filter(
        r => p.x >= r.x && p.x < r.x + r.width && p.y >= r.y && p.y < r.y + r.height
      );
      expect(contains.length).toBe(isSheltered(WORLD, p) ? 1 : 0);
    }
  expect(coveredRectangles(WORLD)).toBe(rects);
});
