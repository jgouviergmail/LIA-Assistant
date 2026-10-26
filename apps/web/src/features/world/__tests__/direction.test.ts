import { describe, expect, it } from 'vitest';
import {
  actorBox,
  actorFace,
  actorPoint,
  headingFromMotion,
  facingFromMotion,
} from '../art/actor-direction';

describe('directional actor geometry', () => {
  it.each([
    [1, 0, 0],
    [0, 1, 1],
    [-1, 0, 2],
    [0, -1, 3],
  ])('faces the actual world displacement (%s, %s)', (x, y, facing) => {
    expect(facingFromMotion({ x, y })).toBe(facing);
    const front = actorBox({ x: 0.3, y: 0.8, width: 0.4, depth: 0.2 }, facing);
    const center = { x: front.x + front.width / 2 - 0.5, y: front.y + front.depth / 2 - 0.5 };
    expect(center.x * x + center.y * y).toBeGreaterThan(0.25);
  });
  it('places facial details on the visible forward face only', () => {
    expect(actorFace(0)).toEqual({ side: true, x: 0.94, y: 0.22 });
    expect(actorFace(1)).toEqual({ side: false, x: 0.22, y: 0.94 });
    expect(actorFace(2)).toBeNull();
    expect(actorFace(3)).toBeNull();
  });
  it('preserves dimensions and center after a full turn', () => {
    const part = { x: 0.2, y: 0.3, width: 0.1, depth: 0.4 };
    let turned = part;
    for (let n = 0; n < 4; n++) turned = actorBox(turned, 0);
    expect(turned.x).toBeCloseTo(part.x);
    expect(turned.y).toBeCloseTo(part.y);
    expect(turned.width).toBeCloseTo(part.width);
    expect(turned.depth).toBeCloseTo(part.depth);
  });
});

it('keeps an equal-axis facing stable across subpixel floating-point roundoff', () => {
  expect(facingFromMotion({ x: -1.2000000000000028, y: 1.1999999999999993 })).toBe(1);
  expect(facingFromMotion({ x: 1.2000000000000028, y: -1.1999999999999993 })).toBe(3);
  expect(facingFromMotion({ x: 1.201, y: 1.2 })).toBe(0);
});

it.each([
  [1, 0],
  [1, 1],
  [0, 1],
  [-1, 1],
  [-1, 0],
  [-1, -1],
  [0, -1],
  [1, -1],
])('aligns the body front with the travelled vector (%s, %s), including diagonals', (x, y) => {
  const heading = headingFromMotion({ x, y }, 0);
  const front = actorPoint({ x: 0.5, y: 1.5 }, heading);
  const length = Math.hypot(x, y);
  expect(front.x - 0.5).toBeCloseTo(x / length);
  expect(front.y - 0.5).toBeCloseTo(y / length);
});
it('keeps the last valid heading at rest and under invalid motion', () => {
  expect(headingFromMotion({ x: 0, y: 0 }, 5)).toBe(5);
  expect(headingFromMotion({ x: Number.NaN, y: 1 }, 5)).toBe(5);
  expect(headingFromMotion({ x: Number.POSITIVE_INFINITY, y: 1 }, 5)).toBe(5);
});
