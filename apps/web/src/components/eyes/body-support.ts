/** Source-calibrated support points keep grounded acting attached to its floor. */
import type { BodyMotionPose } from './body-motion-geometry';
import type { SpiritVariant } from '../spirit/catalogue';
import { VOLUME_SOURCE_EM, volumeProfile, type VolumeCharacter } from './volume/volume-geometry';

type Point = readonly [x: number, y: number];
export interface BodyFootprint {
  readonly left: Point;
  readonly right: Point;
}

type FootedCharacter = 'moss' | 'lumen' | 'bip' | 'boulon' | 'oscar';
/** Solid sole rows and horizontal centres measured on the immutable source alpha.
 * A shadow/transparent margin is not a contact point. Each variant is independent. */
const SOLES: Record<FootedCharacter, readonly [BodyFootprint, BodyFootprint]> = {
  moss: [
    { left: [0.39583, 0.95052], right: [0.60156, 0.95052] },
    { left: [0.35417, 0.92969], right: [0.64265, 0.92969] },
  ],
  lumen: [
    { left: [0.38802, 0.92969], right: [0.60938, 0.92969] },
    { left: [0.36719, 0.91406], right: [0.63972, 0.91406] },
  ],
  bip: [
    { left: [0.40785, 0.9401], right: [0.58232, 0.9401] },
    { left: [0.39041, 0.89323], right: [0.60639, 0.89323] },
  ],
  boulon: [
    { left: [0.34603, 0.94531], right: [0.6465, 0.94531] },
    { left: [0.28689, 0.94531], right: [0.7044, 0.94531] },
  ],
  oscar: [
    { left: [0.43574, 0.97135], right: [0.56027, 0.97135] },
    { left: [0.40698, 0.96615], right: [0.59442, 0.96615] },
  ],
};

function registeredFootprint(
  source: BodyFootprint,
  character: VolumeCharacter,
  variant: SpiritVariant
): BodyFootprint {
  const span = VOLUME_SOURCE_EM * volumeProfile(character, variant).scale;
  const point = ([x, y]: Point): Point => [(x - 0.5) * span, (y - 0.5) * span];
  return { left: point(source.left), right: point(source.right) };
}

const FOOTPRINTS = new Map<string, BodyFootprint>();
for (const character of Object.keys(SOLES) as FootedCharacter[]) {
  for (const variant of ['female', 'male'] as const) {
    FOOTPRINTS.set(
      `${character}/${variant}`,
      registeredFootprint(SOLES[character][Number(variant === 'male')], character, variant)
    );
  }
}
const MONITOR = registeredFootprint(
  { left: [0.5, 0.9140625], right: [0.5, 0.9140625] },
  'monitor',
  'male'
);
/** Floating bodies have no imaginary floor; native screens share their stand. */
export function bodySupportFootprint(
  character: string | undefined,
  variant: string | undefined
): BodyFootprint | null {
  if (character === 'monitor') return MONITOR;
  return FOOTPRINTS.get(`${character}/${variant}`) ?? null;
}

function finiteUnit(value: number, min: number): number {
  return Number.isFinite(value) ? Math.max(min, Math.min(1, value)) : 0;
}

/** Compensate around the selected sole before the existing viewport constraint.
 * This plants the authored support point under body scale/roll; it is not IK or
 * a correction to independently articulated foot geometry. Airborne travel stays
 * unchanged, and the scene's support weight releases contact continuously. */
export function supportBodyMotion(
  pose: BodyMotionPose,
  feet: BodyFootprint | null,
  support: number,
  side: number
): BodyMotionPose {
  const weight = finiteUnit(support, 0);
  if (!feet || weight === 0) return pose;
  const blend = (finiteUnit(side, -1) + 1) / 2;
  const x = feet.left[0] * (1 - blend) + feet.right[0] * blend;
  const y = feet.left[1] * (1 - blend) + feet.right[1] * blend;
  const radians = ((pose.roll % 360) * Math.PI) / 180;
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return {
    ...pose,
    x: pose.x + weight * (x - x * pose.sx * cosine + y * pose.sy * sine),
    y: pose.y + weight * (y - x * pose.sx * sine - y * pose.sy * cosine),
  };
}
