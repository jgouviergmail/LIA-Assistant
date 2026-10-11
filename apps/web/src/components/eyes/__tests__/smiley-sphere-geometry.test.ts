import { describe, expect, it } from 'vitest';
import {
  projectSmileySurface,
  SMILEY_SPHERE_RADIUS,
  smileySphereResolution,
} from '../smiley/sphere-geometry';

describe('Actual spherical Smiley surface', () => {
  it('preserves the approved frontal organ positions and dimensions', () => {
    for (const point of [
      { x: -0.48, y: -0.23 },
      { x: 0.48, y: -0.23 },
      { x: 0, y: 0.45 },
    ]) {
      const surface = projectSmileySurface(point, { yaw: 0, pitch: 0 });
      expect(surface).toMatchObject({ x: point.x, y: point.y, a: 1, b: 0, c: 0, d: 1 });
      expect(surface.z).toBeGreaterThan(1);
    }
  });

  it('keeps the radius constant through every head direction rather than foreshortening a disc', () => {
    for (const yaw of [-0.35, 0, 0.35]) {
      for (const pitch of [-0.22, 0, 0.22]) {
        for (const point of [
          { x: -0.48, y: -0.23 },
          { x: 0.48, y: -0.23 },
          { x: 0, y: 0.45 },
        ]) {
          const surface = projectSmileySurface(point, { yaw, pitch });
          expect(Math.hypot(surface.x, surface.y, surface.z)).toBeCloseTo(SMILEY_SPHERE_RADIUS, 8);
          expect(surface.z).toBeGreaterThan(0);
        }
      }
    }
  });

  it('moves the face around the sphere with independent near/far tangents and no blocked eye', () => {
    const left = projectSmileySurface({ x: -0.48, y: -0.23 }, { yaw: 0.28, pitch: 0 });
    const right = projectSmileySurface({ x: 0.48, y: -0.23 }, { yaw: 0.28, pitch: 0 });
    expect(left.x).toBeGreaterThan(-0.48);
    expect(right.x).toBeGreaterThan(0.48);
    expect(left.a).toBeGreaterThan(right.a);
    expect(right.a).toBeGreaterThan(0.8);
    expect(left.z).toBeGreaterThan(right.z);
  });

  it('retains finite forward-facing anchors during expressive eye travel and malformed inputs', () => {
    for (const point of [
      { x: -2, y: -2 },
      { x: 2, y: 2 },
      { x: Infinity, y: NaN },
    ]) {
      const surface = projectSmileySurface(point, { yaw: 0.35, pitch: -0.22 });
      expect(Object.values(surface).every(Number.isFinite)).toBe(true);
      expect(surface.z).toBeGreaterThan(0);
      expect(Math.hypot(surface.x, surface.y)).toBeLessThan(SMILEY_SPHERE_RADIUS);
    }
  });

  it('bounds the drawing buffer independently of device pixel ratio and display size', () => {
    expect(smileySphereResolution('sm', 1)).toBe(52);
    expect(smileySphereResolution('sm', 2)).toBe(104);
    expect(smileySphereResolution('md', 2)).toBe(156);
    expect(smileySphereResolution('lg', 3)).toBe(192);
    expect(smileySphereResolution('lg', Infinity)).toBe(115);
    expect(smileySphereResolution('xl', 1)).toBe(167);
    expect(smileySphereResolution('xl', 2)).toBe(192);
    expect(smileySphereResolution('xl', 3)).toBe(192);
  });
});
