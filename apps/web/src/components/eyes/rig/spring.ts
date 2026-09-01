/**
 * Analytic damped spring — one scalar channel of the eye rig.
 *
 * Why analytic and not a Euler/Verlet integrator: a background tab, a garbage
 * collection pause or a dropped frame hands the loop a `dt` measured in whole
 * seconds. A numerical integrator explodes there (the classic "the eyes flew
 * off screen after the tab woke up"); the closed-form solution of the damped
 * harmonic oscillator is EXACT at any dt, so it is unconditionally stable and
 * frame-rate independent by construction.
 *
 * Parameters are the two an animator actually reasons with:
 *  - `frequency` — how fast the pose wants to arrive (in Hz; omega = 2*pi*f)
 *  - `damping`   — the damping RATIO: < 1 rings (joy), = 1 lands clean
 *                  (a reflex), > 1 drags in (sadness).
 */

/** A channel's instantaneous state. Immutable: every step returns a new one. */
export interface SpringState {
  readonly value: number;
  readonly velocity: number;
}

/** The two knobs. `frequency <= 0` means "no physics": snap to the target. */
export interface SpringConfig {
  readonly frequency: number;
  readonly damping: number;
}

/** Position tolerance under which a channel counts as settled. */
export const REST_EPSILON = 1e-4;

/** Velocity tolerance under which a channel counts as settled. */
export const REST_VELOCITY_EPSILON = 1e-3;

/** Below this distance from 1, the damping ratio is treated as critical:
 * the underdamped and overdamped forms both divide by a term that vanishes
 * there, so the critical form is the numerically stable one near 1. */
const CRITICAL_BAND = 1e-3;

/**
 * Advance one channel by `dtMs` milliseconds toward `target`.
 *
 * Returns the state unchanged for a non-positive dt (a clamped clock, a
 * duplicated frame), so callers never have to guard the clock themselves.
 */
export function springStep(
  state: SpringState,
  target: number,
  config: SpringConfig,
  dtMs: number
): SpringState {
  if (!(dtMs > 0)) return state;
  if (!(config.frequency > 0)) return { value: target, velocity: 0 };

  const dt = dtMs / 1000;
  const omega = 2 * Math.PI * config.frequency;
  const zeta = Math.max(0, config.damping);
  // Solve around the offset from the target: the equation is homogeneous
  // there, and the target is re-added at the end.
  const x0 = state.value - target;
  const v0 = state.velocity;

  if (Math.abs(zeta - 1) < CRITICAL_BAND) {
    const decay = Math.exp(-omega * dt);
    const c2 = v0 + omega * x0;
    const x = (x0 + c2 * dt) * decay;
    const v = (c2 - omega * (x0 + c2 * dt)) * decay;
    return { value: target + x, velocity: v };
  }

  if (zeta < 1) {
    const omegaD = omega * Math.sqrt(1 - zeta * zeta);
    const decay = Math.exp(-zeta * omega * dt);
    const c1 = x0;
    const c2 = (v0 + zeta * omega * x0) / omegaD;
    const cos = Math.cos(omegaD * dt);
    const sin = Math.sin(omegaD * dt);
    const x = decay * (c1 * cos + c2 * sin);
    const v = decay * (-zeta * omega * (c1 * cos + c2 * sin) + omegaD * (c2 * cos - c1 * sin));
    return { value: target + x, velocity: v };
  }

  const root = omega * Math.sqrt(zeta * zeta - 1);
  const r1 = -omega * zeta + root;
  const r2 = -omega * zeta - root;
  const c2 = (v0 - r1 * x0) / (r2 - r1);
  const c1 = x0 - c2;
  const e1 = Math.exp(r1 * dt);
  const e2 = Math.exp(r2 * dt);
  return {
    value: target + c1 * e1 + c2 * e2,
    velocity: c1 * r1 * e1 + c2 * r2 * e2,
  };
}

/** True when the channel has both arrived and stopped — the runtime sleeps
 * only when EVERY channel says yes. */
export function isSpringAtRest(state: SpringState, target: number): boolean {
  return (
    Math.abs(state.value - target) <= REST_EPSILON &&
    Math.abs(state.velocity) <= REST_VELOCITY_EPSILON
  );
}
