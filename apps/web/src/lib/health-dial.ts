/**
 * The scale of a health dial (owner, 2026-11-06).
 *
 * Three bands of equal length whose edges are the bounds the card colours a figure by, so a figure
 * and its place on the dial cannot disagree. Where a scale stops is a drawing choice, a last band
 * as long as the others: a value past it stays at the end, and its figure says the rest.
 */
import type { HealthKind } from '@/types/briefing';

export type HealthTone = 'red' | 'orange' | 'green';

/** A band of the dial, in the order it is drawn. */
export type HealthBand = 0 | 1 | 2;

export const HEALTH_BANDS: readonly HealthBand[] = [0, 1, 2];

export interface HealthScale {
  /** Where the dial starts. */
  from: number;
  /** Where it ends. */
  to: number;
  /** The last value of the first band, and the first of the last. */
  bounds: readonly [number, number];
  /** What each band means for this measure: more steps are better, a lower pulse is. */
  tones: readonly [HealthTone, HealthTone, HealthTone];
}

export const HEALTH_SCALES: Readonly<Record<HealthKind, HealthScale>> = {
  steps: { from: 0, to: 15000, bounds: [5000, 10000], tones: ['red', 'orange', 'green'] },
  heart_rate: { from: 50, to: 110, bounds: [70, 90], tones: ['green', 'orange', 'red'] },
};

/** How much of the dial a band gives up at an inner edge: its round end and a gap. */
const BAND_GAP = 0.025;

/** @returns The band a value stands in, a bound belonging to the band at its end of the dial. */
export function bandOf(scale: HealthScale, value: number): HealthBand {
  if (value <= scale.bounds[0]) return 0;
  return value >= scale.bounds[1] ? 2 : 1;
}

export function toneOf(scale: HealthScale, value: number): HealthTone {
  return scale.tones[bandOf(scale, value)];
}

/** @returns Where a value stands on the dial, from 0 to 1. */
export function dialPosition(scale: HealthScale, value: number): number {
  const position = (value - scale.from) / (scale.to - scale.from);
  return Math.min(Math.max(position, 0), 1);
}

/** @returns What a band covers of the dial, from 0 to 1. */
export function bandArc(band: number): { from: number; to: number } {
  const last = HEALTH_BANDS.length - 1;
  return {
    from: band === 0 ? 0 : band / HEALTH_BANDS.length + BAND_GAP,
    to: band === last ? 1 : (band + 1) / HEALTH_BANDS.length - BAND_GAP,
  };
}
