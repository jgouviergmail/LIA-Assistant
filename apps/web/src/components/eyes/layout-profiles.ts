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
export interface AvatarLayoutProfile extends LayoutLandmarks {
  readonly family: AvatarLayoutFamily;
  readonly variant: SpiritVariant;
  readonly neckY: number;
  readonly scarfWidthEm: number;
  readonly scarf: ScarfFit;
}

function landmarks(crownY: number, faceY: number, accessoryScale: number): LayoutLandmarks {
  return { crownY, faceY, accessoryScale };
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
    '--avatar-face-half-width':
      profile.family === 'monitor'
        ? `calc(${nativeSpan} * var(--monitor-face-scale, 0.38))`
        : `calc${nativeSpan}`,
  };
}
