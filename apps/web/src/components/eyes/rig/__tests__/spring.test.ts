/**
 * Damped-spring integrator — the physical heart of the eye rig.
 *
 * These tests pin the four properties the animation depends on:
 *  - exactness (frame-rate independence: the analytic solution, not Euler)
 *  - stability at any dt (a throttled tab hands us dt in whole seconds)
 *  - the three damping regimes an animator actually asks for
 *  - velocity CONTINUITY across a target change — the property that makes an
 *    interrupted emotion read as a creature changing its mind rather than a
 *    UI transition being cut.
 */

import { describe, it, expect } from 'vitest';
import {
  isSpringAtRest,
  REST_EPSILON,
  springStep,
  type SpringConfig,
  type SpringState,
} from '@/components/eyes/rig/spring';

const CRITICAL: SpringConfig = { frequency: 2, damping: 1 };
const BOUNCY: SpringConfig = { frequency: 2, damping: 0.35 };
const SLUGGISH: SpringConfig = { frequency: 2, damping: 2 };

function run(
  state: SpringState,
  target: number,
  config: SpringConfig,
  steps: number,
  dtMs = 16
): SpringState[] {
  const trace: SpringState[] = [];
  let current = state;
  for (let i = 0; i < steps; i += 1) {
    current = springStep(current, target, config, dtMs);
    trace.push(current);
  }
  return trace;
}

describe('springStep', () => {
  it('leaves a settled spring untouched', () => {
    const settled: SpringState = { value: 1, velocity: 0 };
    expect(springStep(settled, 1, CRITICAL, 16)).toEqual(settled);
  });

  it('is the identity for a zero or negative dt', () => {
    const moving: SpringState = { value: 0.2, velocity: 3 };
    expect(springStep(moving, 1, CRITICAL, 0)).toEqual(moving);
    expect(springStep(moving, 1, CRITICAL, -8)).toEqual(moving);
  });

  it('never overshoots when critically damped', () => {
    const trace = run({ value: 0, velocity: 0 }, 1, CRITICAL, 200);
    expect(Math.max(...trace.map(s => s.value))).toBeLessThanOrEqual(1);
    expect(trace[trace.length - 1].value).toBeCloseTo(1, 4);
  });

  it('overshoots and rings when underdamped', () => {
    const trace = run({ value: 0, velocity: 0 }, 1, BOUNCY, 200);
    expect(Math.max(...trace.map(s => s.value))).toBeGreaterThan(1.15);
    // It comes back: an overshoot that never returns is a bug, not a bounce.
    expect(trace[trace.length - 1].value).toBeCloseTo(1, 3);
  });

  it('approaches monotonically, and slower than critical, when overdamped', () => {
    const trace = run({ value: 0, velocity: 0 }, 1, SLUGGISH, 200);
    for (let i = 1; i < trace.length; i += 1) {
      expect(trace[i].value).toBeGreaterThanOrEqual(trace[i - 1].value - 1e-9);
    }
    const reach90 = (t: SpringState[]) => t.findIndex(s => s.value >= 0.9);
    expect(reach90(trace)).toBeGreaterThan(
      reach90(run({ value: 0, velocity: 0 }, 1, CRITICAL, 200))
    );
  });

  it('stays finite and converges for a multi-second dt (throttled tab)', () => {
    const jumped = springStep({ value: 0, velocity: 0 }, 1, BOUNCY, 5000);
    expect(Number.isFinite(jumped.value)).toBe(true);
    expect(Number.isFinite(jumped.velocity)).toBe(true);
    expect(jumped.value).toBeCloseTo(1, 6);
    expect(jumped.velocity).toBeCloseTo(0, 6);
  });

  it('is frame-rate independent: one big step equals many small ones', () => {
    const start: SpringState = { value: 0, velocity: 0 };
    const oneStep = springStep(start, 1, BOUNCY, 100);
    const manySteps = run(start, 1, BOUNCY, 10, 10)[9];
    expect(manySteps.value).toBeCloseTo(oneStep.value, 9);
    expect(manySteps.velocity).toBeCloseTo(oneStep.velocity, 9);
  });

  it('carries velocity across a target change (no reset mid-flight)', () => {
    const moving = run({ value: 0, velocity: 0 }, 1, BOUNCY, 8)[7];
    expect(moving.velocity).toBeGreaterThan(0.5);
    // Retargeting must not touch the current state — only where it is heading.
    const retargeted = springStep(moving, -1, BOUNCY, 0);
    expect(retargeted.velocity).toBe(moving.velocity);
    // ...and the very next frame still moves in the old direction (inertia).
    const next = springStep(moving, -1, BOUNCY, 16);
    expect(next.value).toBeGreaterThan(moving.value);
  });

  it('snaps to the target for a non-positive frequency (reduced-motion rail)', () => {
    const snapped = springStep({ value: 0, velocity: 4 }, 1, { frequency: 0, damping: 1 }, 16);
    expect(snapped).toEqual({ value: 1, velocity: 0 });
  });
});

describe('isSpringAtRest', () => {
  it('is true only when both the offset and the velocity are negligible', () => {
    expect(isSpringAtRest({ value: 1, velocity: 0 }, 1)).toBe(true);
    expect(isSpringAtRest({ value: 1 + REST_EPSILON * 10, velocity: 0 }, 1)).toBe(false);
    expect(isSpringAtRest({ value: 1, velocity: 1 }, 1)).toBe(false);
  });
});
