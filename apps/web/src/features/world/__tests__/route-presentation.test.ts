import { describe, expect, it } from 'vitest';
import { routePresentation } from '../route-presentation';

describe('private navigation projection', () => {
  it('follows only the current path and never mutates or recomputes it', () => {
    const path = [
      { x: 2, y: 3 },
      { x: 5, y: 6 },
    ];
    const origin = { x: 1, y: 1 };
    expect(routePresentation(origin, path, true)).toEqual([origin, ...path]);
    expect(routePresentation(origin, path, false)).toEqual([]);
    expect(routePresentation(origin, [], true)).toEqual([]);
    expect(routePresentation(origin, [{ x: 8, y: 9 }], true)).toEqual([origin, { x: 8, y: 9 }]);
    expect(path).toEqual([
      { x: 2, y: 3 },
      { x: 5, y: 6 },
    ]);
  });
  it('bounds drawing work and rejects non-finite points', () => {
    expect(
      routePresentation(
        { x: 0, y: 0 },
        Array.from({ length: 1000 }, (_, x) => ({ x, y: 0 })),
        true
      ).length
    ).toBeLessThanOrEqual(129);
    expect(routePresentation({ x: NaN, y: 0 }, [{ x: 1, y: 0 }], true)).toEqual([]);
  });
});
