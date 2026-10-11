import type { SpiritVariant } from './catalogue';

/** Original sculpts share the native facial rig and the assistant's gender preference. */
export const COMPANION_CHARACTERS = [
  'spirit',
  'moss',
  'lumen',
  'nimbo',
  'orbit',
  'bip',
  'boulon',
  'oscar',
] as const;
export type CompanionCharacter = (typeof COMPANION_CHARACTERS)[number];

/** Published artwork is immutable; refreshed bodies receive a new version. */
export const COMPANION_BODY_VERSIONS = {
  spirit: 2,
  moss: 2,
  lumen: 2,
  nimbo: 1,
  orbit: 1,
  bip: 1,
  boulon: 1,
  oscar: 1,
} as const satisfies Record<CompanionCharacter, number>;

/** Every hybrid keeps a native round-eye face; material belongs to its own skin. */
export const COMPANION_FACE_STYLES = {
  spirit: 'billes',
  moss: 'billes',
  lumen: 'billes',
  nimbo: 'billes',
  orbit: 'billes',
  bip: 'billes',
  boulon: 'billes',
  oscar: 'billes',
} as const satisfies Record<CompanionCharacter, 'billes' | 'cozmo'>;

export function companionBodyAsset(character: CompanionCharacter, variant: SpiritVariant) {
  return `/avatars/${character}/v${COMPANION_BODY_VERSIONS[character]}/${variant}/body.webp`;
}
