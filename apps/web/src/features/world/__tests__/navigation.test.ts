import { describe, expect, it } from 'vitest';
import { findRoute, nearbyWalkable } from '../navigation';
import { directionFromScreen } from '../simulation';
import type { Point } from '../types';

function length(from: Point, route: Point[]): number {
  let total = 0;
  for (const point of route) {
    total += Math.hypot(point.x - from.x, point.y - from.y);
    from = point;
  }
  return total;
}

function grid() {
  return { width: 12, height: 12, blocked: new Uint8Array(144) };
}

describe('natural, collision-safe click navigation', () => {
  it('crosses open ground directly instead of making a stair-shaped detour', () => {
    const from = { x: 1.3, y: 1.7 };
    const to = { x: 9.2, y: 7.4 };
    const route = findRoute(grid(), from, to);
    expect(route.at(-1)).toEqual(to);
    expect(length(from, route)).toBeCloseTo(Math.hypot(7.9, 5.7), 8);
  });

  it('follows a floor axis without snapping an off-center avatar sideways', () => {
    const from = { x: 1.3, y: 2.4 };
    const route = findRoute(grid(), from, { x: 9.1, y: 2.4 });
    expect(route.length).toBeGreaterThan(0);
    expect(route.every(point => Math.abs(point.y - 2.4) < 1e-8)).toBe(true);
    expect(length(from, route)).toBeCloseTo(7.8, 8);
  });

  it('routes around a wall and keeps the entire avatar clear at every segment', () => {
    const nav = grid();
    for (let y = 0; y < 8; y++) nav.blocked[y * nav.width + 5] = 1;
    const from = { x: 2.3, y: 3.2 };
    const to = { x: 8.6, y: 3.1 };
    const route = findRoute(nav, from, to);
    expect(route.at(-1)).toEqual(to);
    let previous = from;
    for (const point of route) {
      const distance = Math.hypot(point.x - previous.x, point.y - previous.y);
      for (let n = 0; n <= 500; n++) {
        const x = previous.x + ((point.x - previous.x) * n) / 500;
        const y = previous.y + ((point.y - previous.y) * n) / 500;
        // Authored wall occupies x=[5,6], y=[0,8]; body has a 0.22 half-width.
        expect(x < 4.78 || x > 6.22 || y > 8.22).toBe(true);
      }
      expect(distance).toBeGreaterThan(0);
      previous = point;
    }
  });

  it('cannot squeeze diagonally between two touching obstacles', () => {
    const nav = grid();
    nav.blocked[1] = 1;
    nav.blocked[nav.width] = 1;
    expect(findRoute(nav, { x: 0.5, y: 0.5 }, { x: 2.5, y: 2.5 })).toEqual([]);
  });

  it('still respects its exploration budget and rejects malformed endpoints', () => {
    const from = { x: 0.5, y: 0.5 };
    expect(findRoute(grid(), from, { x: 10.5, y: 10.5 }, 1)).toEqual([]);
    expect(findRoute(grid(), from, { x: NaN, y: 4 })).toEqual([]);
    expect(findRoute(grid(), { x: -1, y: 2 }, from)).toEqual([]);
  });
});

it('lets combined direction keys follow the isometric floor axes at constant speed', () => {
  expect(directionFromScreen({ x: 1, y: 1 })).toEqual({ x: 1, y: 0 });
  expect(directionFromScreen({ x: -1, y: 1 })).toEqual({ x: 0, y: 1 });
  expect(directionFromScreen({ x: -1, y: -1 })).toEqual({ x: -1, y: 0 });
  expect(directionFromScreen({ x: 1, y: -1 })).toEqual({ x: 0, y: -1 });
});

it('keeps an unobstructed pointer destination rather than snapping it to a tile center', () => {
  expect(nearbyWalkable(grid(), { x: 3.2, y: 2.7 })).toEqual({ x: 3.2, y: 2.7 });
});

it('moves a blocked click to a nearby place that fits the whole body', () => {
  const nav = grid();
  nav.blocked[2 * nav.width + 3] = 1;
  const point = nearbyWalkable(nav, { x: 3.3, y: 2.7 });
  expect(point).not.toBeNull();
  expect(findRoute(nav, { x: 1.4, y: 1.8 }, point!).at(-1)).toEqual(point);
  expect(point!.x < 2.78 || point!.x > 4.22 || point!.y < 1.78 || point!.y > 3.22).toBe(true);
});

it('refuses a destination when every nearby position is blocked or outside the map', () => {
  const nav = grid();
  nav.blocked.fill(1);
  expect(nearbyWalkable(nav, { x: 2.1, y: 2.9 })).toBeNull();
  expect(nearbyWalkable(grid(), { x: -12, y: -12 })).toBeNull();
  expect(nearbyWalkable(grid(), { x: NaN, y: 3 })).toBeNull();
});
