import { expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { fountainToss, paintFountainToss } from '../art/fountain-toss';
import { FOUNTAIN_IMPACT } from '../decor-presentation';
it('throws from the arrived avatar hand, ends the coin at impact, then expands the water rings', () => {
  const beat = {
    id: 'fountain',
    action: 'fountain' as const,
    point: { x: 20, y: 10 },
    origin: { x: 18, y: 10 },
    elevation: 0.3,
    phase: 0,
  };
  expect(fountainToss(beat).coin).toBeNull();
  expect(fountainToss({ ...beat, phase: 0.2 }).coin).not.toBeNull();
  expect(fountainToss({ ...beat, phase: 0.4 }).ripple).toBe(0);
  expect(fountainToss({ ...beat, phase: FOUNTAIN_IMPACT }).coin).toBeNull();
  expect(fountainToss({ ...beat, phase: 0.8 }).ripple).toBeGreaterThan(
    fountainToss({ ...beat, phase: 0.6 }).ripple
  );
  expect(fountainToss({ ...beat, origin: undefined, phase: 0.2 }).coin).toBeNull();
});
it('holds one still ring set under reduced motion while the full motion expands it', () => {
  const beat = {
    id: 'fountain',
    action: 'fountain' as const,
    point: { x: 20, y: 10 },
    origin: { x: 18, y: 10 },
    elevation: 0.3,
    phase: 0,
  };
  function rings(phase: number, reduced: boolean) {
    const ellipse = vi.fn();
    const c = canvasContext({ ellipse });
    paintFountainToss(c, { ...beat, phase }, reduced);
    return { radii: ellipse.mock.calls.map(call => call[2]), alpha: c.globalAlpha };
  }
  const early = rings(0.6, true),
    late = rings(0.95, true);
  expect(early.radii).toHaveLength(3);
  expect(late).toEqual(early);
  expect(rings(0.95, false).radii[0]).toBeGreaterThan(rings(0.6, false).radii[0]);
  expect(rings(0.4, true).radii).toEqual([]);
});
