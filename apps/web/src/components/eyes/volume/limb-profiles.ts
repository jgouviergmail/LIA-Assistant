/** Joint landmarks measured in normalized coordinates on each published body image. */
import type { LimbChannel } from '../rig/channels';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import type { VolumeCharacter } from './volume-geometry';

type Point = readonly [number, number];
export interface LimbJoint {
  channel: LimbChannel;
  pivot: Point;
  direction: Point;
  blend: number;
  limit: number;
}
export interface LimbChain {
  parent: LimbJoint | null;
  distal: LimbJoint | null;
  /** Outside this rectangle the source art is rigid, including the face and collar. */
  region: readonly [number, number, number, number];
  feather: number;
}
type Pair = readonly [number, number];
function joint(
  channel: LimbChannel,
  pivot: Point,
  direction: Point,
  blend: number,
  limit: number
): LimbJoint {
  return { channel, pivot, direction, blend, limit };
}
function arms(
  pivot: Point,
  wrist: Point | null,
  region: LimbChain['region'],
  limits: Pair,
  blend = 0.045
): LimbChain[] {
  return [false, true].map(right => {
    const point = (p: Point): Point => [right ? 1 - p[0] : p[0], p[1]];
    const dx = wrist ? wrist[0] - pivot[0] : -1;
    const dy = wrist ? wrist[1] - pivot[1] : 0.25;
    const length = Math.hypot(dx, dy);
    const direction: Point = [(right ? -dx : dx) / length, dy / length];
    return {
      parent: joint(right ? 'armR' : 'armL', point(pivot), direction, blend, limits[0]),
      distal: wrist
        ? joint(right ? 'wristR' : 'wristL', point(wrist), direction, 0.025, limits[1])
        : null,
      region: right
        ? [1 - region[2], region[1], 1.1, region[3]]
        : [-0.1, region[1], region[2], region[3]],
      feather: wrist ? 0.075 : 0.06,
    };
  });
}
function feet(
  ankle: Point,
  hip: Point | null,
  region: LimbChain['region'],
  limits: Pair,
  blend = 0.05
): LimbChain[] {
  return [false, true].map(right => {
    const point = (p: Point): Point => [right ? 1 - p[0] : p[0], p[1]];
    return {
      parent: hip ? joint(right ? 'legR' : 'legL', point(hip), [0, 1], 0.04, limits[0]) : null,
      distal: joint(right ? 'footR' : 'footL', point(ankle), [0, 1], blend, limits[1]),
      region: right
        ? [1 - region[2], region[1], 1 - region[0], 1.1]
        : [region[0], region[1], region[2], 1.1],
      feather: 0.06,
    };
  });
}

/** Immutable per-variant measurements; unsupported anatomy is explicitly empty. */
const PROFILES: Record<VolumeCharacter, readonly [readonly LimbChain[], readonly LimbChain[]]> = {
  monitor: [[], []],
  // Both lateral projections are one continuous ring, not independently moving limbs.
  orbit: [[], []],
  spirit: [
    arms([0.245, 0.62], null, [0.12, 0.55, 0.26, 0.76], [12, 0], 0.035),
    arms([0.16, 0.6], null, [0.045, 0.54, 0.18, 0.73], [10, 0], 0.035),
  ],
  nimbo: [
    arms([0.265, 0.675], null, [0.025, 0.59, 0.28, 0.84], [7, 0], 0.1),
    arms([0.25, 0.665], null, [0.015, 0.59, 0.27, 0.83], [7, 0], 0.1),
  ],
  moss: [
    [
      ...arms([0.235, 0.65], null, [0.13, 0.58, 0.25, 0.76], [12, 0], 0.03),
      ...feet([0.39, 0.89], null, [0.28, 0.875, 0.48, 0.99], [0, 10]),
    ],
    [
      ...arms([0.155, 0.63], null, [0.045, 0.56, 0.17, 0.75], [12, 0], 0.03),
      ...feet([0.345, 0.855], null, [0.245, 0.84, 0.45, 0.98], [0, 10]),
    ],
  ],
  lumen: [
    [
      ...arms([0.235, 0.64], null, [0.125, 0.56, 0.25, 0.755], [12, 0], 0.03),
      ...feet([0.385, 0.865], null, [0.285, 0.85, 0.48, 0.98], [0, 10]),
    ],
    [
      ...arms([0.16, 0.645], null, [0.04, 0.565, 0.18, 0.76], [12, 0], 0.035),
      ...feet([0.36, 0.86], null, [0.25, 0.845, 0.47, 0.97], [0, 10]),
    ],
  ],
  bip: [
    [
      ...arms([0.345, 0.705], [0.305, 0.76], [0.21, 0.675, 0.38, 0.835], [15, 10]),
      ...feet([0.4, 0.89], [0.405, 0.82], [0.25, 0.835, 0.485, 0.995], [10, 10]),
    ],
    [
      ...arms([0.32, 0.675], [0.255, 0.735], [0.15, 0.64, 0.37, 0.82], [15, 10]),
      ...feet([0.39, 0.845], [0.4, 0.79], [0.23, 0.82, 0.485, 0.965], [10, 10]),
    ],
  ],
  boulon: [
    [
      ...arms([0.22, 0.615], [0.185, 0.715], [0.105, 0.58, 0.245, 0.83], [13, 10]),
      ...feet([0.35, 0.87], [0.355, 0.83], [0.2, 0.83, 0.465, 0.99], [8, 10]),
    ],
    [
      ...arms([0.175, 0.585], [0.115, 0.7], [0.005, 0.55, 0.2, 0.815], [11, 8]),
      ...feet([0.285, 0.855], [0.3, 0.825], [0.15, 0.815, 0.435, 0.985], [8, 10], 0.07),
    ],
  ],
  oscar: [
    [
      ...arms([0.365, 0.61], [0.325, 0.78], [0.27, 0.585, 0.39, 0.855], [12, 10], 0.055),
      ...feet([0.44, 0.93], [0.445, 0.83], [0.32, 0.855, 0.495, 0.995], [10, 10]),
    ],
    [
      ...arms([0.34, 0.61], [0.285, 0.79], [0.205, 0.585, 0.36, 0.87], [11, 9], 0.06),
      ...feet([0.42, 0.93], [0.425, 0.835], [0.29, 0.87, 0.495, 0.995], [10, 10]),
    ],
  ],
};

export function limbProfile(
  character: VolumeCharacter,
  variant: SpiritVariant
): readonly LimbChain[] {
  return PROFILES[character][Number(variant === 'male')];
}
