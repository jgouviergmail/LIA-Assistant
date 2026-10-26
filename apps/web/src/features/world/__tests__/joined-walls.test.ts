import { expect, it } from 'vitest';
import { joinWalls } from '../house-authoring';
import { wallProfile } from '../art/wall-profile';
import { propTextureKey } from '../art/prop-style';

it('deduplicates crossing walls into one connected solid and respects real openings', () => {
  const walls = joinWalls([
    { x: 0, y: 2, length: 5, axis: 'x', height: 0.85, tone: 'teal', openings: [1] },
    { x: 2, y: 0, length: 5, axis: 'y', height: 0.85, tone: 'teal' },
  ]);
  expect(walls.filter(p => p.x === 2 && p.y === 2)).toHaveLength(1);
  expect(walls.some(p => p.x === 1 && p.y === 2)).toBe(false);
  const center = walls.find(p => p.x === 2 && p.y === 2)!;
  expect(center.wallConnections).toBe(11);
  expect(propTextureKey(center, false, false)).not.toBe(
    propTextureKey({ ...center, wallConnections: 5 }, false, false)
  );
});

it('all wall junctions have one nondegenerate bounded contour with no duplicate vertices', () => {
  for (let mask = 0; mask < 16; mask++) {
    const points = wallProfile(mask, 0.24);
    expect(points.length).toBeGreaterThanOrEqual(4);
    expect(new Set(points.map(p => p.x + ':' + p.y)).size).toBe(points.length);
    let area = 0;
    for (let i = 0; i < points.length; i++) {
      const a = points[i],
        b = points[(i + 1) % points.length];
      expect(a.x >= 0 && a.x <= 1 && a.y >= 0 && a.y <= 1).toBe(true);
      expect(a.x === b.x || a.y === b.y).toBe(true);
      area += a.x * b.y - b.x * a.y;
    }
    const arms = [1, 2, 4, 8].filter(bit => mask & bit).length;
    expect(area / 2).toBeCloseTo(0.24 * 0.24 + arms * 0.38 * 0.24, 8);
  }
});
