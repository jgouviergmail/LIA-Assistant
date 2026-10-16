import { describe, expect, it } from 'vitest';
import { unobstructedPlacement } from '../eyes-placement';

const viewport = { width: 390, height: 800, minimumTop: 80 };
const size = { width: 120, height: 140 };
const preferred = { left: 246, top: 532 };

describe('default companion placement', () => {
  it('keeps its current place while the underlying actions remain free', () => {
    expect(unobstructedPlacement(preferred, size, viewport, [])).toEqual(preferred);
  });

  it.each([
    {
      edge: 'left viewport edge',
      requested: { left: 0, top: 150 },
      bounds: viewport,
      expected: { left: 8, top: 150 },
    },
    {
      edge: 'header boundary',
      requested: { left: 150, top: 0 },
      bounds: viewport,
      expected: { left: 150, top: 80 },
    },
    {
      edge: 'panned visual viewport',
      requested: { left: 0, top: 50 },
      bounds: { ...viewport, minimumLeft: 100, minimumTop: 120 },
      expected: { left: 108, top: 120 },
    },
  ])(
    'keeps the preferred $edge nearby when no control blocks it',
    ({ requested, bounds, expected }) => {
      expect(unobstructedPlacement(requested, size, bounds, [])).toEqual(expected);
    }
  );

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

it('finds the narrow safe band between mobile controls at 360px', () => {
  const point = unobstructedPlacement(
    { left: 20, top: 100 },
    { width: 100, height: 70 },
    { width: 360, height: 800, minimumTop: 80 },
    [
      { left: 0, top: 80, right: 360, bottom: 170 },
      { left: 0, top: 260, right: 360, bottom: 800 },
    ]
  );
  expect(point).not.toBeNull();
  expect(point?.top).toBeGreaterThanOrEqual(178);
  expect((point?.top ?? 0) + 70).toBeLessThanOrEqual(252);
});

it('keeps the companion inside a horizontally panned visual viewport', () => {
  const point = unobstructedPlacement(
    { left: 8, top: 90 },
    size,
    { width: 300, height: 500, minimumLeft: 100, minimumTop: 80 },
    []
  );
  expect(point?.left).toBeGreaterThanOrEqual(108);
  expect((point?.left ?? 0) + size.width).toBeLessThanOrEqual(292);
});
