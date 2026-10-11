/**
 * Eye-style registry — single source of truth for the selectable looks of the
 * expressive-eyes widget (settings › preferences › personalization).
 *
 * Every selectable style declares its renderer and six localized labels.
 * Native skins also declare their CSS material and complete rig geometry.
 * Hybrid characters compose original 3D bodies with a real native facial rig.
 */

import { COMPANION_CHARACTERS } from '@/components/spirit/companion-catalogue';

export const RIG_EYE_STYLE_IDS = [
  'cozmo',
  'capsules',
  'billes',
  'amande',
  'traits',
  'anneaux',
  'smiley',
] as const;

export type RigEyeStyleId = (typeof RIG_EYE_STYLE_IDS)[number];

export const HYBRID_EYE_STYLE_IDS = COMPANION_CHARACTERS;
export const EYE_STYLE_IDS = [...RIG_EYE_STYLE_IDS, ...HYBRID_EYE_STYLE_IDS] as const;

export type EyeStyleId = (typeof EYE_STYLE_IDS)[number];

export const EYE_STYLE_RENDERERS = {
  cozmo: 'rig',
  capsules: 'rig',
  billes: 'rig',
  amande: 'rig',
  traits: 'rig',
  anneaux: 'rig',
  smiley: 'rig',
  spirit: 'hybrid',
  moss: 'hybrid',
  lumen: 'hybrid',
  nimbo: 'hybrid',
  orbit: 'hybrid',
  bip: 'hybrid',
  boulon: 'hybrid',
  oscar: 'hybrid',
} as const satisfies Record<EyeStyleId, 'rig' | 'hybrid'>;

/** The initial avatar selected for visitors and new installations. */
export const DEFAULT_EYE_STYLE: EyeStyleId = 'bip';

/** Raw rig hosts require native geometry. Hybrid selections route through EyesFace. */
export const DEFAULT_RIG_EYE_STYLE: RigEyeStyleId = 'smiley';

/** Geometry boundary: the hybrid renderer explicitly selects a real native skin. */
export function isRigEyeStyle(value: EyeStyleId): value is RigEyeStyleId {
  return EYE_STYLE_RENDERERS[value] === 'rig';
}

/** Strict runtime guard (persisted values, future deep links). */
export function isValidEyeStyle(value: unknown): value is EyeStyleId {
  return typeof value === 'string' && (EYE_STYLE_IDS as readonly string[]).includes(value);
}
