import { expect, it } from 'vitest';
import { floorEdgeBounds } from '../art/floor-boundary';
import { WORLD } from '../definition';
import type { WorldProp } from '../types';
it('ends an indoor floor at its outside wall face while leaving room seams and door thresholds intact', () => {
  const base = WORLD.props.find(p => p.kind === 'partition');
  if (!base) throw new Error('No authored wall');
  const wall = (x: number, y: number): WorldProp => ({ ...base, id: x + ':' + y, x, y });
  const scene = {
    ...WORLD,
    zones: [
      {
        id: 'arrival' as const,
        x: 0,
        y: 0,
        width: 3,
        height: 3,
        tone: 'cream' as const,
        covered: true,
        arrival: { x: 1.5, y: 1.5 },
      },
    ],
    props: [wall(2, 1), wall(1, 1), wall(1, 0)],
  };
  const edges = floorEdgeBounds(scene);
  expect(edges.get('2:1')?.width).toBeLessThan(1);
  expect(edges.get('2:1')?.width).toBeGreaterThan(0.5);
  expect(edges.get('1:0')?.y).toBeGreaterThan(0);
  expect(edges.has('1:1')).toBe(false);
  expect(edges.has('2:2')).toBe(false);
});

it('never inserts a grass strip where the indoor floor meets the paved terrace', () => {
  const terrace = WORLD.zones.find(zone => zone.id === 'terrace')!;
  const edges = floorEdgeBounds(WORLD);
  const threshold = WORLD.props.filter(
    prop =>
      prop.kind === 'partition' &&
      prop.y === terrace.y - 1 &&
      prop.x >= terrace.x &&
      prop.x < terrace.x + terrace.width
  );
  expect(threshold.length).toBeGreaterThan(0);
  for (const wall of threshold) {
    const crop = edges.get(wall.x + ':' + wall.y);
    expect(crop ? crop.y + crop.height : 1, wall.id).toBe(1);
  }
});
