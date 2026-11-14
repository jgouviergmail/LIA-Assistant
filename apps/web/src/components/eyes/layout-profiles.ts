/** Static landmarks in the common 2.6em frame; motion remains entirely native. */
import type { CSSProperties } from 'react';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import type { CompanionCharacter } from '@/components/spirit/companion-catalogue';
import type { EyeStyleId } from './eye-styles';
import { MONITOR_SCREEN } from './monitor-geometry';
import { volumeProfile, VOLUME_SOURCE_EM } from './volume/volume-geometry';
import { scarfFrame, type ScarfFit } from './volume/scarf-fit';
import { WEATHER_COLD_MAX } from './rig/ambient';

export type AvatarLayoutFamily = CompanionCharacter | 'monitor';
interface LayoutLandmarks {
  /** Fractions of the complete frame, including a crown that extends above it. */
  readonly crownY: number;
  readonly faceY: number;
  readonly accessoryScale: number;
}
/** Where the frost laurel is worn: the centre of its square, a share of the frame
 * like the landmarks, and its scale (1: the artwork's 1.6em square). */
interface LaurelFit {
  readonly y: number;
  readonly scale: number;
}
export interface AvatarLayoutProfile extends LayoutLandmarks {
  readonly family: AvatarLayoutFamily;
  readonly variant: SpiritVariant;
  readonly neckY: number;
  readonly scarfWidthEm: number;
  readonly scarf: ScarfFit;
  readonly laurel: LaurelFit;
  /** Where a drop falling down the middle meets the head, a share of the frame. */
  readonly headTopY: number;
  /** Where a caught flake settles: the centre of the root of the nose. */
  readonly flakeY: number;
}

function landmarks(crownY: number, faceY: number, accessoryScale: number): LayoutLandmarks {
  return { crownY, faceY, accessoryScale };
}

function laurel(y: number, scale: number): LaurelFit {
  return { y, scale };
}

/** Crown measurements use the delivered opaque silhouette, not diffuse shadows.
 * Hybrid artwork is registered at 113%; face landmarks retain approved native
 * anchors. The scarf and other props have their own calibrated gendered scale. */
const LANDMARKS = {
  spirit: {
    male: landmarks(0.135, 0.52405, 1),
    female: landmarks(0, 0.52405, 0.84),
  },
  moss: {
    male: landmarks(0.082, 0.52405, 1),
    female: landmarks(-0.018, 0.52405, 0.86),
  },
  lumen: {
    male: landmarks(0.1, 0.52405, 0.98),
    female: landmarks(-0.012, 0.52405, 0.83),
  },
  nimbo: {
    male: landmarks(0.176, 0.49, 1.1),
    female: landmarks(0.106, 0.49, 1.04),
  },
  orbit: {
    male: landmarks(0.129, 0.48, 1.02),
    female: landmarks(0.047, 0.48, 0.93),
  },
  bip: {
    male: landmarks(0.117, 0.43, 0.9),
    female: landmarks(0.041, 0.43, 0.83),
  },
  boulon: {
    male: landmarks(-0.012, 0.43, 1),
    female: landmarks(-0.012, 0.43, 0.9),
  },
  oscar: {
    male: landmarks(-0.012, 0.336, 0.6),
    female: landmarks(-0.053, 0.354, 0.57),
  },
  monitor: {
    male: landmarks(0.135, MONITOR_SCREEN.y + MONITOR_SCREEN.height / 2, 0.88),
    female: landmarks(0.135, MONITOR_SCREEN.y + MONITOR_SCREEN.height / 2, 0.88),
  },
} as const satisfies Record<AvatarLayoutFamily, Record<SpiritVariant, LayoutLandmarks>>;

/** The frost laurel is WORN on top of the head: each band rests on the painted
 * edge (its foot neither in the air nor deeper in the head than the band is
 * thick), the whole crown ends above the face, and the middle stays free for a
 * tuft, a leaf or a bow. Chosen on the paint of every head with its face (the
 * eyes and brows are the rig's, not the artwork's): as large as the bare artwork
 * suggests where the head leaves room, seated inside the range these rules accept
 * and at least 0.04 em from either end of it, so every engine paints it inside.
 * The crown landmark cannot seat it: a silhouette's top is its ribbon or its tuft
 * (ADR-294, follow-up of 2026-11-13). */
const LAURELS = {
  spirit: { male: laurel(0.23, 1.2), female: laurel(0.08, 0.8) },
  moss: { male: laurel(0.195, 1.15), female: laurel(0.26, 0.9) },
  lumen: { male: laurel(0.225, 1.15), female: laurel(0.09, 0.9) },
  nimbo: { male: laurel(0.205, 1.15), female: laurel(0.205, 1.1) },
  orbit: { male: laurel(0.14, 1.15), female: laurel(0.185, 1.15) },
  bip: { male: laurel(0.09, 1.15), female: laurel(0.14, 1.1) },
  boulon: { male: laurel(0.11, 1), female: laurel(0.195, 0.95) },
  oscar: { male: laurel(0.03, 0.8), female: laurel(-0.03, 0.75) },
  monitor: { male: laurel(0.05, 0.95), female: laurel(0.05, 0.95) },
} as const satisfies Record<AvatarLayoutFamily, Record<SpiritVariant, LaurelFit>>;

/** Where a drop falling down the middle of the frame meets each head: the first
 * painted row anywhere across the drop's own width (0.13 em), measured on the
 * paint of every head (xl, a static pose, ADR-294 follow-up of 2026-11-13). What
 * it meets first is what it lands on — the edge of a ribbon when one reaches the
 * middle, as on Spirit's. Neither landmark above can say it: the crown is a
 * silhouette's top, often off the middle, and the laurel seat is where two bands
 * rest on its sides. The first drop of a rain lands here. */
const HEAD_TOPS = {
  spirit: { male: 0.143, female: 0.001 },
  moss: { male: 0.082, female: -0.017 },
  lumen: { male: 0.116, female: 0.007 },
  nimbo: { male: 0.176, female: 0.155 },
  orbit: { male: 0.125, female: 0.094 },
  bip: { male: 0.119, female: 0.088 },
  boulon: { male: -0.011, female: 0.025 },
  oscar: { male: -0.011, female: -0.05 },
  monitor: { male: 0.134, female: 0.134 },
} as const satisfies Record<AvatarLayoutFamily, Record<SpiritVariant, number>>;

/** Where a caught flake settles on each face: the root of the nose, between the
 * brows and the eyes' tops, on the middle column. Measured on the paint of every
 * head with its face (xl, a static pose): below the eyes the mouth leaves no room
 * on most heads (0.008 em on two of them) and between them the eyes leave 0.13 to
 * 0.20 em, so the root of the nose is the one place on every face where a flake
 * covers no eye, brow or mouth. The lowest centre where a 0.16 em flake fits with
 * 0.02 em to spare, raised 0.03 of the frame for the face's own motion (ADR-294,
 * follow-up of 2026-11-13). */
const FLAKE_YS = {
  spirit: { male: 0.414, female: 0.402 },
  moss: { male: 0.414, female: 0.402 },
  lumen: { male: 0.414, female: 0.402 },
  nimbo: { male: 0.384, female: 0.372 },
  orbit: { male: 0.372, female: 0.36 },
  bip: { male: 0.336, female: 0.318 },
  boulon: { male: 0.336, female: 0.276 },
  oscar: { male: 0.197, female: 0.206 },
  // The screen's six drawn faces: one band is free on all of them, below the
  // eyes — the tip of the nose — from 0.444 to 0.453; its middle.
  monitor: { male: 0.449, female: 0.449 },
} as const satisfies Record<AvatarLayoutFamily, Record<SpiritVariant, number>>;

const STYLE_FAMILY = {
  cozmo: 'monitor',
  capsules: 'monitor',
  billes: 'monitor',
  amande: 'monitor',
  traits: 'monitor',
  anneaux: 'monitor',
  spirit: 'spirit',
  moss: 'moss',
  lumen: 'lumen',
  nimbo: 'nimbo',
  orbit: 'orbit',
  bip: 'bip',
  boulon: 'boulon',
  oscar: 'oscar',
} as const satisfies Record<EyeStyleId, AvatarLayoutFamily>;

export function avatarLayoutProfile(
  style: EyeStyleId | 'monitor',
  variant: SpiritVariant
): AvatarLayoutProfile {
  const family = style === 'monitor' ? style : STYLE_FAMILY[style];
  const collar = volumeProfile(family, variant).collar;
  return {
    family,
    variant,
    ...LANDMARKS[family][variant],
    neckY: collar.centerY / VOLUME_SOURCE_EM + 0.5,
    scarfWidthEm: scarfFrame(collar).width,
    scarf: collar,
    laurel: LAURELS[family][variant],
    headTopY: HEAD_TOPS[family][variant],
    flakeY: FLAKE_YS[family][variant],
  };
}

type AvatarLayoutStyle = CSSProperties & Record<`--avatar-${string}`, string>;
/** Both fitted bodies and bare-eye defaults publish the same garment mapping. */
export function scarfLayoutStyle(fit: ScarfFit, prefix = 'avatar-scarf') {
  const scarf = scarfFrame(fit);
  return {
    [`--${prefix}-width`]: `${scarf.width}em`,
    [`--${prefix}-top`]: `${scarf.top}em`,
    [`--${prefix}-height`]: `${scarf.height}em`,
    [`--${prefix}-split`]: `${scarf.split}em`,
    [`--${prefix}-band-scale`]: `${scarf.bandScale}em`,
    [`--${prefix}-tail-scale`]: `${scarf.tailScale}em`,
    [`--${prefix}-tail-offset`]: `${scarf.tailOffset - scarf.split}em`,
    [`--${prefix}-opacity-scale`]: `${1 / WEATHER_COLD_MAX}`,
  };
}
/** Eye span stays tied to the actual skin, including the latest Oscar spacing. */
export function avatarLayoutStyle(profile: AvatarLayoutProfile): AvatarLayoutStyle {
  const nativeSpan = '(var(--eye-w, 1.3em) + var(--eye-gap, 0.45em) * 0.5)';
  return {
    '--avatar-crown-y': `${Number((profile.crownY * 100).toFixed(3))}%`,
    '--avatar-face-y': `${Number((profile.faceY * 100).toFixed(3))}%`,
    '--avatar-neck-y': `${Number((profile.neckY * 100).toFixed(3))}%`,
    ...scarfLayoutStyle(profile.scarf),
    '--avatar-accessory-scale': String(profile.accessoryScale),
    '--avatar-laurel-y': `${Number((profile.laurel.y * 100).toFixed(3))}%`,
    '--avatar-laurel-scale': String(profile.laurel.scale),
    '--avatar-head-top-y': `${Number((profile.headTopY * 100).toFixed(3))}%`,
    '--avatar-flake-y': `${Number((profile.flakeY * 100).toFixed(3))}%`,
    '--avatar-face-half-width':
      profile.family === 'monitor'
        ? `calc(${nativeSpan} * var(--monitor-face-scale, 0.38))`
        : `calc${nativeSpan}`,
  };
}
