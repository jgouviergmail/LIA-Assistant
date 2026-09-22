/**
 * The stylesheet's arithmetic, in pixels — for tests that must speak about
 * what a viewer SEES rather than about channel values.
 *
 * Every formula here mirrors one `calc()` in `styles/eyes.css`. They are kept
 * in one place so a test about "the mouth moves by under a pixel" and a test
 * about "the brow reaches this high" cannot drift from each other, and the
 * sibling `css-boundary` test keeps the sheet itself honest about the channels
 * these read.
 */

import type { ChannelValues } from '@/components/eyes/rig/channels';

/** Font sizes of the three widget presets (`.lia-eyes--sm/md/lg`). */
export const SIZE_PX = { sm: 20, md: 30, lg: 44 } as const;

/** What the mouth and the brows draw, in pixels, for one frame. */
export interface FaceMetrics {
  /** `.lia-mouth-shape` height: ink + arc depth + opening. */
  mouthHeight: number;
  /** `.lia-mouth` width: the style span times the width channel. */
  mouthWidth: number;
  /** The corner tilt, in degrees, already turned the right way up. */
  mouthTilt: number;
  /** The vertical position of each brow, in pixels (positive = lower). */
  browY: { left: number; right: number };
  /** The height of each brow box — its thickness plus the arch. */
  browHeight: { left: number; right: number };
}

/** Mirrors the Cozmo tokens of the sheet (`--mouth-span`, `--mouth-ink`,
 * `--eye-h`). */
const MOUTH_SPAN_EM = 0.92;

const EYE_H_EM = 1.05;
const BROW_THICKNESS_EM = (0.3 * 10) / 36;
const BROW_ARCH_EM = (0.3 * 18) / 36;

/**
 * Where the visible top edge of one eye sits below the top of its box, as a
 * fraction of the box height — the sheet's `top:` on `.lia-eye-brow`: the
 * shape is scaled by `sy` around `oy` and then clipped by `lidTop`.
 */
function visibleTopFraction(values: Readonly<ChannelValues>, side: 'L' | 'R'): number {
  const sy = values[`sy${side}`];
  return (values[`oy${side}`] / 100) * (1 - sy) + (values[`lidTop${side}`] / 100) * sy;
}

function curve(arc: number): number {
  return Math.min(1, Math.max(0, arc));
}

export function faceMetrics(values: Readonly<ChannelValues>, px: number): FaceMetrics {
  const lean = values.mouthSkew;
  const upper = 32 + values.mouthCurve * 16 - values.mouthArc ** 2 * 9;
  const depth = 6 + values.mouthArc ** 2 * 32;
  const opening = values.mouthOpen * (80 - upper - depth);
  return {
    mouthHeight: (((depth + opening) * 0.75 * 0.68) / 80) * px,
    mouthWidth: MOUTH_SPAN_EM * values.mouthW * px,
    mouthTilt:
      (Math.atan2((14 * lean * 0.68) / 80, MOUTH_SPAN_EM * values.mouthW * 0.9) * 180) / Math.PI,
    browY: {
      left: (visibleTopFraction(values, 'L') * EYE_H_EM + values.browYL) * px,
      right: (visibleTopFraction(values, 'R') * EYE_H_EM + values.browYR) * px,
    },
    browHeight: {
      left:
        (BROW_THICKNESS_EM * Math.max(0.94, Math.min(1.06, values.browSL)) +
          curve(values.browArcL) * BROW_ARCH_EM) *
        px,
      right:
        (BROW_THICKNESS_EM * Math.max(0.94, Math.min(1.06, values.browSR)) +
          curve(values.browArcR) * BROW_ARCH_EM) *
        px,
    },
  };
}

/** Peak-to-peak spread of a series. */
export function spread(values: readonly number[]): number {
  return Math.max(...values) - Math.min(...values);
}
