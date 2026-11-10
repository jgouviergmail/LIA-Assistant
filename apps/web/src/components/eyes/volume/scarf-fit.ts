/** Measured landmarks of the immutable front art, shared by cloth and CSS fallback. */
import { WEATHER_COLD_MAX } from '../rig/ambient';

export const SCARF_ART = {
  url: '/avatars/scarf/v1/front.webp',
  bandTop: 89 / 192,
  bandCenter: 105.5 / 192,
  bandBottom: 122 / 192,
  tailStart: 0.65,
  tailTip: 145 / 192,
} as const;

/** One activation/opacity rule for cloth allocation and complete-avatar readiness. */
export function scarfOpacity(cold: number): number {
  return Number.isFinite(cold) && cold > 0.02 ? Math.min(1, cold / WEATHER_COLD_MAX) : 0;
}

export interface ScarfFit {
  /** Registered neck center and half-width, in the native em frame. */
  centerY: number;
  radiusX: number;
  /** Thickness at the center of the woven band, independent of neck width. */
  height: number;
  /** Hanging length below the band, independent of its thickness. */
  tailDrop: number;
  /** A full circumference, registered to a measured anatomical cross section. */
  wrap?: {
    radiusZ: number;
    power: number;
    frontDrop: number;
    knotScale: number;
  };
}

/** Bare expressive eyes have no anatomical body, but retain a bounded weather prop. */
export const DEFAULT_SCARF_FIT: ScarfFit = {
  centerY: 0.754,
  radiusX: 0.886,
  height: 0.22,
  tailDrop: 0.18,
};

/** Two affine texture slices meet below the band, where only the tail is opaque. */
export function scarfFrame(fit: ScarfFit) {
  const bandScale = fit.height / (SCARF_ART.bandBottom - SCARF_ART.bandTop);
  const tailScale = fit.tailDrop / (SCARF_ART.tailTip - SCARF_ART.tailStart);
  const split = SCARF_ART.tailStart * bandScale;
  const top = fit.centerY - SCARF_ART.bandCenter * bandScale;
  return {
    width: fit.radiusX * 2.2,
    top,
    height: split + (1 - SCARF_ART.tailStart) * tailScale,
    bandScale,
    tailScale,
    split,
    tailOffset: split - SCARF_ART.tailStart * tailScale,
  };
}

export function mapScarfUv(fit: ScarfFit, u: number, v: number) {
  const frame = scarfFrame(fit);
  return {
    x: (u - 0.5) * frame.width,
    y:
      frame.top +
      (v <= SCARF_ART.tailStart ? v * frame.bandScale : frame.tailOffset + v * frame.tailScale),
  };
}
