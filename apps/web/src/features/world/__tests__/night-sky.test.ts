import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { expect, it, vi } from 'vitest';
import { paintStars } from '../art/stars';
import { ambientStrength } from '../art/lighting';
import { createCamera } from '../geometry';
import type { Quality } from '../types';

it('keeps indoor furniture readable at night without leaving it in full daylight', () => {
  for (const phase of ['noon', 'unknown'] as const) {
    expect(ambientStrength(phase, true)).toBe(0);
    expect(ambientStrength(phase, false)).toBe(0);
  }
  for (const phase of ['dawn', 'evening', 'night'] as const) {
    expect(ambientStrength(phase, true)).toBeGreaterThan(0);
    expect(ambientStrength(phase, true)).toBeLessThan(0.2);
    expect(ambientStrength(phase, true)).toBeLessThan(ambientStrength(phase, false));
  }
});

it.each<Quality>(['low', 'balanced', 'high'])(
  'bounds the %s star field and keeps positions stable when the camera moves',
  quality => {
    const c = canvasContext({
      save: vi.fn(),
      restore: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillRect: vi.fn(),
    });
    const context = c;
    const camera = createCamera({ width: 390, height: 844 }, { x: 0, y: 0 });
    paintStars(context, camera, 'noon', quality);
    expect(c.arc).not.toHaveBeenCalled();
    paintStars(context, camera, 'night', quality);
    const positions = c.arc.mock.calls.map(args => args.slice(0, 3));
    expect(positions.length).toBeGreaterThan(50);
    expect(positions.length).toBeLessThanOrEqual(180);
    for (const [x, y, radius] of positions) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThan(camera.width);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThan(camera.height);
      expect(radius).toBeGreaterThan(0);
      expect(radius).toBeLessThan(2);
    }
    c.arc.mockClear();
    paintStars(context, { ...camera, center: { x: 900, y: 900 }, zoom: 2 }, 'night', quality);
    expect(c.arc.mock.calls.map(args => args.slice(0, 3))).toEqual(positions);
    expect(c.save).toHaveBeenCalledTimes(2);
    expect(c.restore).toHaveBeenCalledTimes(2);
  }
);
