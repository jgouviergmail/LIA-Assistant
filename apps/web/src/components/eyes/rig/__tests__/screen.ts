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

/** Mirrors the Cozmo tokens of the sheet (`--mouth-span`, `--mouth-ink`). */
const MOUTH_SPAN_EM = 0.92;
const MOUTH_INK_EM = 0.1;
const BROW_THICKNESS_EM = 0.13;
const BROW_ARCH_EM = 0.14;

function curve(arc: number): number {
  return Math.min(1, Math.max(0, arc));
}

export function faceMetrics(values: Readonly<ChannelValues>, px: number): FaceMetrics {
  const lean = values.mouthSkew * values.mouthFlip;
  return {
    mouthHeight: (MOUTH_INK_EM + values.mouthArc * 0.26 + values.mouthOpen * 0.5) * px,
    mouthWidth: MOUTH_SPAN_EM * values.mouthW * px,
    mouthTilt: lean * 14,
    browY: { left: values.browYL * px, right: values.browYR * px },
    browHeight: {
      left: (BROW_THICKNESS_EM + curve(values.browArcL) * BROW_ARCH_EM) * px,
      right: (BROW_THICKNESS_EM + curve(values.browArcR) * BROW_ARCH_EM) * px,
    },
  };
}

/** Peak-to-peak spread of a series. */
export function spread(values: readonly number[]): number {
  return Math.max(...values) - Math.min(...values);
}
