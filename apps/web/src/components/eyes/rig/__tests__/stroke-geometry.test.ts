import { describe, expect, it } from 'vitest';
import { createEyeRig } from '../runtime';
import { strokeContours } from '../stroke-geometry';

describe('drawn eyes morph instead of changing CSS recipes', () => {
  it.each(['traits', 'anneaux'] as const)(
    '%s changes line, arch and ring continuously',
    styleId => {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId, family: 'calm' },
      });
      for (const expression of ['joy', 'sad', 'surprise', 'sleep', 'neutral'] as const) {
        let previous = strokeContours(rig.values(), 'L')
          .upper.match(/-?\d+(?:\.\d+)?/g)!
          .map(Number);
        rig.setPose({ expression, styleId, family: 'calm' });
        for (let time = 0; time < 2500; time += 8) {
          rig.step(8);
          const contour = strokeContours(rig.values(), 'L');
          const coordinates = contour.upper.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
          expect(Math.max(...coordinates.map((n, i) => Math.abs(n - previous[i])))).toBeLessThan(3);
          expect(contour.width).toBeGreaterThan(0);
          previous = coordinates;
        }
      }
    }
  );
});
