import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { WORLD } from '../definition';
import { Painter } from '../art/painter';
import { paintTree } from '../art/trees';
import { propStyleVariant } from '../art/prop-style';
import type { Season } from '../season';
import type { Tone } from '../types';

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
});
afterEach(() => vi.restoreAllMocks());

function treeColors(variant: number, tone: Tone, season: Season) {
  const authored = WORLD.props.find(
    prop => prop.kind === 'tree' && propStyleVariant(prop) === variant
  );
  if (!authored) throw new Error('Missing authored tree family');
  const painter = new Painter(1, 1, 4, 1, season);
  const polygons = vi.spyOn(painter, 'polygon');
  paintTree(painter, { ...authored, tone });
  const calls = polygons.mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  expect(calls.every(([points]) => points.every(point => Number.isFinite(point.x + point.y)))).toBe(
    true
  );
  return {
    colors: [
      ...new Set(calls.flatMap(([, color]) => (typeof color === 'string' ? [color] : []))),
    ].sort(),
    polygons: calls.length,
  };
}

it.each([0, 1, 2])(
  'keeps tree family %s geometry stable while applying seasonal foliage and blossoms',
  variant => {
    for (const tone of ['sage', 'clay'] as const) {
      const neutral = treeColors(variant, tone, 'neutral');
      for (const season of ['spring', 'summer', 'autumn', 'winter'] as const) {
        const current = treeColors(variant, tone, season);
        expect(current.polygons).toBe(neutral.polygons);
        if (variant === 1 && tone === 'sage' && season !== 'winter')
          expect(current.colors).toEqual(neutral.colors);
        else expect(current.colors).not.toEqual(neutral.colors);
      }
    }
  }
);
