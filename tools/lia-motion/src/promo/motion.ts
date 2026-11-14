/**
 * Motion vocabulary of the film: deterministic functions of the frame only.
 *
 * Every animation reads the current frame and nothing else, so any frame can
 * be rendered alone, in any order, by any worker.
 */
import { Easing, interpolate, spring } from 'remotion';
import { FPS } from './timing';

export const clamp = (v: number, lo = 0, hi = 1): number => Math.min(hi, Math.max(lo, v));
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

/** Expressive ease-out for entrances (fast start, long soft landing). */
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
/** Symmetric ease for camera moves. */
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);
/** Accelerating ease for exits and for a thread racing to a downbeat. */
export const easeIn = Easing.bezier(0.55, 0, 0.9, 0.4);

/** 0 -> 1 between `start` and `start + duration`, clamped, eased. */
export const ramp = (
  frame: number,
  start: number,
  duration: number,
  easing: (t: number) => number = easeOut,
): number =>
  interpolate(frame, [start, start + Math.max(1, duration)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });

/** A window: rises over `fadeIn` from `start`, falls over `fadeOut` before `end`. */
export const windowed = (
  frame: number,
  start: number,
  end: number,
  fadeIn = 12,
  fadeOut = 12,
): number => Math.min(ramp(frame, start, fadeIn), 1 - ramp(frame, end - fadeOut, fadeOut, easeIn));

export type SpringConfig = { damping: number; stiffness: number; mass?: number };
export const SNAPPY: SpringConfig = { damping: 15, stiffness: 190, mass: 0.9 };
export const SOFT: SpringConfig = { damping: 22, stiffness: 120, mass: 1 };
export const BOUNCY: SpringConfig = { damping: 10, stiffness: 160, mass: 0.8 };

/** A spring starting at `start` (0 before it). Overshoot follows the config. */
export const pop = (frame: number, start: number, config: SpringConfig = SNAPPY): number =>
  frame < start ? 0 : spring({ frame: frame - start, fps: FPS, config: { mass: 1, ...config } });

/** Deterministic pseudo-random in [0, 1) from an integer seed. */
export const rand = (seed: number): number => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
};

/** Text revealed character by character between two frames. */
export const typed = (text: string, frame: number, start: number, end: number): string => {
  const chars = Array.from(text);
  const n = Math.floor(chars.length * clamp((frame - start) / Math.max(1, end - start)));
  return chars.slice(0, n).join('');
};

/** A pulse that peaks on each beat and decays over `decay` frames. */
export const beatPulse = (frame: number, period: number, decay = 14, offset = 0): number => {
  const local = (((frame - offset) % period) + period) % period;
  return Math.exp(-local / Math.max(1, decay / 3));
};
