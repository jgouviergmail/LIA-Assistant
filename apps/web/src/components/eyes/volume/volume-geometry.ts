/** Shallow anatomical proxy surfaces. Frontal art is retained; hidden anatomy is approximate. */
import type { ChannelValues } from '../rig/channels';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import { alphaOutlineMesh } from './volume-outline';
import { silhouetteDepth } from './volume-distance';

export const VOLUME_CHARACTERS = [
  'spirit',
  'moss',
  'lumen',
  'nimbo',
  'orbit',
  'bip',
  'boulon',
  'oscar',
  'monitor',
] as const;
export type VolumeCharacter = (typeof VOLUME_CHARACTERS)[number];
export type VolumeSurfaceKind = 'left' | 'right' | 'mouth' | 'neck-front' | 'neck-back';
export interface VolumePoint {
  x: number;
  y: number;
  z: number;
}
export interface VolumePose {
  yaw: number;
  pitch: number;
}
export interface VolumeMesh {
  vertices: Float32Array;
  indices: Uint16Array;
}
export interface VolumeMask {
  width: number;
  height: number;
  alpha: Uint8Array;
}
export interface VolumeLobe {
  x: number;
  y: number;
  rx: number;
  ry: number;
  depth: number;
  box?: boolean;
}
export interface CollarProfile {
  centerY: number;
  radiusX: number;
  radiusZ: number;
  height: number;
  centerZ?: number;
  conformSphereRadius?: number;
  tail?: boolean;
}
export interface VolumeProfile {
  character: VolumeCharacter;
  variant: SpiritVariant;
  scale: number;
  lobes: readonly VolumeLobe[];
  collar: CollarProfile;
  alphaDistance?: { width: number; height: number; values: Float32Array };
}
const EM = 2.6;
const finite = (value: number) => (Number.isFinite(value) ? value : 0);

function lobe(
  x: number,
  y: number,
  rx: number,
  ry: number,
  depth: number,
  box = false
): VolumeLobe {
  return { x: (x - 0.5) * EM, y: (y - 0.5) * EM, rx: rx * EM, ry: ry * EM, depth, box };
}

function anatomy(character: VolumeCharacter, male: boolean): VolumeLobe[] {
  const breadth = male ? 1.08 : 0.94;
  if (character === 'nimbo')
    return [
      lobe(0.5, 0.41, 0.3, 0.3, 0.64),
      lobe(0.21, 0.56, 0.16, 0.23, 0.48),
      lobe(0.79, 0.56, 0.16, 0.23, 0.48),
      lobe(0.5, 0.65, 0.32, 0.15, 0.52),
      lobe(0.5, 0.26, 0.16, 0.13, 0.45),
      lobe(0.35, 0.75, 0.14, 0.08, 0.28),
      lobe(0.65, 0.75, 0.14, 0.08, 0.28),
    ];
  if (character === 'orbit')
    return [
      lobe(0.5, 0.48, male ? 0.37 : 0.32, 0.4, 0.77),
      lobe(0.5, 0.63, 0.44, 0.1, 0.8),
      lobe(0.16, 0.54, 0.115, 0.145, 0.22),
      lobe(0.84, 0.54, 0.115, 0.145, 0.22),
      lobe(0.5, 0.71, 0.29, 0.1, 0.5),
      lobe(0.5, 0.31, 0.26, 0.23, 0.6),
    ];
  if (character === 'boulon')
    return [
      lobe(0.5, 0.34, 0.32 * breadth, 0.25, 0.5, true),
      lobe(0.5, 0.63, 0.39 * breadth, 0.16, 0.44, true),
      lobe(0.15, 0.64, 0.09, 0.19, 0.24),
      lobe(0.85, 0.64, 0.09, 0.19, 0.24),
      lobe(0.38, 0.87, 0.1, 0.07, 0.27),
      lobe(0.62, 0.87, 0.1, 0.07, 0.27),
      lobe(0.86, 0.23, 0.11, 0.13, 0.24),
      lobe(0.5, 0.12, 0.08, 0.07, 0.24),
    ];
  if (character === 'monitor')
    return [
      lobe(0.5, 0.42, 0.425, 0.27, 0.26, true),
      lobe(0.5, 0.72, 0.065, 0.17, 0.16, true),
      lobe(0.5, 0.91, 0.23, 0.045, 0.29, true),
      lobe(0.86, 0.22, 0.035, 0.1, 0.14),
    ];
  if (character === 'oscar')
    return [
      lobe(0.5, male ? 0.33 : 0.35, 0.175, 0.17, 0.37),
      lobe(0.5, 0.66, 0.21 * breadth, 0.24, 0.26),
      lobe(0.27, 0.62, 0.075, 0.21, 0.17),
      lobe(0.73, 0.62, 0.075, 0.21, 0.17),
      lobe(0.41, 0.91, 0.08, 0.04, 0.24),
      lobe(0.59, 0.91, 0.08, 0.04, 0.24),
      lobe(0.5, 0.435, 0.03, 0.035, 0.43),
      lobe(0.5, 0.145, 0.2, 0.08, 0.23, true),
    ];
  if (character === 'bip')
    return [
      lobe(0.5, 0.405, 0.33 * breadth, 0.245, 0.48, true),
      lobe(0.5, 0.73, 0.21 * breadth, 0.2, 0.3, true),
      lobe(0.19, 0.67, 0.07, 0.17, 0.19),
      lobe(0.81, 0.67, 0.07, 0.17, 0.19),
      lobe(0.36, 0.92, 0.09, 0.035, 0.28),
      lobe(0.64, 0.92, 0.09, 0.035, 0.28),
      lobe(0.5, 0.115, 0.05, 0.075, 0.16),
      lobe(0.5, 0.62, 0.09, 0.035, 0.33),
    ];
  const depth = male ? 0.62 : 0.53;
  return [
    lobe(0.5, 0.53, 0.33 * breadth, 0.4, depth),
    lobe(0.5, 0.395, 0.285 * breadth, 0.23, depth * 0.96),
    lobe(0.17, 0.65, 0.08, 0.075, 0.2),
    lobe(0.83, 0.65, 0.08, 0.075, 0.2),
    lobe(0.38, 0.91, 0.085, 0.04, 0.25),
    lobe(0.62, 0.91, 0.085, 0.04, 0.25),
    lobe(0.44, 0.115, 0.11, 0.09, 0.16),
    lobe(0.6, 0.155, 0.085, 0.09, 0.14),
  ];
}

export function volumeProfile(character: VolumeCharacter, variant: SpiritVariant): VolumeProfile {
  const male = variant === 'male';
  // Frontal cross sections measured on the published RGBA art at this y,
  // including the113% body registration and .025em cloth clearance.
  // The monitor has one shared body; its physical collar is shared too.
  type CollarMeasurements = readonly [number, number, number, number];
  const measurements: Record<VolumeCharacter, readonly [CollarMeasurements, CollarMeasurements]> = {
    spirit: [
      [0.78, 0.851, 0.405, 0.175],
      [0.775, 1.035, 0.44, 0.175],
    ],
    moss: [
      [0.795, 0.851, 0.4, 0.17],
      [0.78, 0.981, 0.43, 0.17],
    ],
    lumen: [
      [0.78, 0.836, 0.415, 0.18],
      [0.765, 0.997, 0.45, 0.18],
    ],
    nimbo: [
      [0.805, 1.173, 0.43, 0.18],
      [0.765, 1.203, 0.47, 0.18],
    ],
    orbit: [
      [0.79, 0.805, 0.44, 0.18],
      [0.755, 0.867, 0.48, 0.18],
    ],
    bip: [
      [0.68, 0.714, 0.305, 0.15],
      [0.67, 0.752, 0.33, 0.15],
    ],
    boulon: [
      [0.7, 0.981, 0.315, 0.16],
      [0.7, 1.05, 0.34, 0.16],
    ],
    oscar: [
      [0.58, 0.262, 0.244, 0.14],
      [0.59, 0.453, 0.265, 0.14],
    ],
    monitor: [
      [0.79, 0.188, 0.156, 0.13],
      [0.79, 0.188, 0.156, 0.13],
    ],
  };
  const [y, radiusX, depth, height] = measurements[character][Number(male)];
  const collar: CollarProfile = {
    centerY: (y - 0.5) * EM,
    radiusX,
    radiusZ: depth,
    height,
    tail: true,
  };
  return {
    character,
    variant,
    scale: character === 'monitor' ? 1 : 1.13,
    lobes: anatomy(character, variant === 'male'),
    collar,
  };
}

export function volumePose(
  values: Readonly<ChannelValues>,
  character: VolumeCharacter
): VolumePose {
  const radians = Math.PI / 180;
  return {
    yaw:
      Math.max(-1.3, Math.min(1.3, finite(values.headYaw))) *
        (character === 'monitor' ? 22 : 16) *
        radians +
      0,
    pitch:
      Math.max(-1.3, Math.min(1.3, finite(values.headPitch))) *
        (character === 'monitor' ? -14 : -10) *
        radians +
      0,
  };
}

export function volumeDepth(profile: VolumeProfile, x: number, y: number): number {
  let depth = 0.018;
  for (const item of profile.lobes) {
    const power = item.box ? 4 : 2;
    const radius =
      1 -
      Math.abs((finite(x) - item.x) / item.rx) ** power -
      Math.abs((finite(y) - item.y) / item.ry) ** power;
    if (radius <= 0) continue;
    const height = item.box ? 0.86 + 0.14 * Math.sqrt(radius) : Math.sqrt(radius);
    depth = Math.max(depth, item.depth * height);
  }
  return depth * silhouetteDepth(profile, finite(x), finite(y));
}

export function rotateVolumePoint(point: VolumePoint, pose: VolumePose): VolumePoint {
  const sy = Math.sin(finite(pose.yaw)),
    cy = Math.cos(finite(pose.yaw));
  const sp = Math.sin(finite(pose.pitch)),
    cp = Math.cos(finite(pose.pitch));
  const x = finite(point.x) * cy + finite(point.z) * sy,
    z = finite(point.z) * cy - finite(point.x) * sy;
  return { x, y: finite(point.y) * cp - z * sp, z: finite(point.y) * sp + z * cp };
}

export function projectVolumeSurface(
  profile: VolumeProfile,
  point: { x: number; y: number },
  pose: VolumePose
) {
  const h = 0.002,
    z = volumeDepth(profile, point.x, point.y);
  const dx =
    (volumeDepth(profile, point.x + h, point.y) - volumeDepth(profile, point.x - h, point.y)) /
    (2 * h);
  const dy =
    (volumeDepth(profile, point.x, point.y + h) - volumeDepth(profile, point.x, point.y - h)) /
    (2 * h);
  const position = rotateVolumePoint({ ...point, z }, pose);
  const horizontal = rotateVolumePoint({ x: 1, y: 0, z: dx }, pose);
  const vertical = rotateVolumePoint({ x: 0, y: 1, z: dy }, pose);
  return { ...position, a: horizontal.x, b: horizontal.y, c: vertical.x, d: vertical.y };
}

/** An eyeball stays in its orbit. Its frame belongs to the skull, not the
 * neighbouring cheek's surface gradient, which would stretch the near globe
 * and flatten the far one. Both eyes share the same rigid frontal axes. */
export function projectEyeSocket(
  profile: VolumeProfile,
  point: { x: number; y: number },
  pose: VolumePose
) {
  const position = rotateVolumePoint({ ...point, z: volumeDepth(profile, point.x, point.y) }, pose);
  const horizontal = rotateVolumePoint({ x: 1, y: 0, z: 0 }, pose);
  const vertical = rotateVolumePoint({ x: 0, y: 1, z: 0 }, pose);
  return { ...position, a: horizontal.x, b: horizontal.y, c: vertical.x, d: vertical.y };
}

/** Two sampled surfaces joined around all four boundaries form one closed hull. */
export function volumeMesh(profile: VolumeProfile, grid = 24): VolumeMesh {
  const side = grid + 1,
    count = side * side;
  const vertices = new Float32Array(count * 2 * 8);
  for (let layer = 0; layer < 2; layer++)
    for (let row = 0; row < side; row++)
      for (let col = 0; col < side; col++) {
        const u = col / grid,
          v = row / grid,
          x = (u - 0.5) * EM * profile.scale,
          y = (v - 0.5) * EM * profile.scale;
        const z = volumeDepth(profile, x, y) * (layer ? -1 : 1);
        const dx =
          (volumeDepth(profile, x + 0.002, y) - volumeDepth(profile, x - 0.002, y)) / 0.004;
        const dy =
          (volumeDepth(profile, x, y + 0.002) - volumeDepth(profile, x, y - 0.002)) / 0.004;
        const sign = layer ? -1 : 1,
          len = Math.hypot(dx, dy, 1);
        vertices.set(
          [x, y, z, -dx / len, -dy / len, sign / len, u, v],
          (layer * count + row * side + col) * 8
        );
      }
  const triangles: number[] = [];
  for (let layer = 0; layer < 2; layer++)
    for (let row = 0; row < grid; row++)
      for (let col = 0; col < grid; col++) {
        const a = layer * count + row * side + col,
          b = a + 1,
          c = a + side,
          d = c + 1;
        triangles.push(a, b, d, a, d, c);
      }
  const rim = rectangleRim(grid, side);
  for (let i = 0; i < rim.length; i++) {
    const a = rim[i],
      b = rim[(i + 1) % rim.length];
    triangles.push(a, b, b + count, a, b + count, a + count);
  }
  return { vertices, indices: new Uint16Array(triangles) };
}
function rectangleRim(grid: number, side: number) {
  const rim: number[] = [];
  for (let col = 0; col < grid; col++) rim.push(col);
  for (let row = 0; row < grid; row++) rim.push(row * side + grid);
  for (let col = grid; col > 0; col--) rim.push(grid * side + col);
  for (let row = grid; row > 0; row--) rim.push(row * side);
  return rim;
}

/** A closed hull of the physical alpha footprint; source shadows remain non-physical. */
export function visibleVolumeMesh(
  profile: VolumeProfile,
  mask: VolumeMask,
  grid = profile.character === 'monitor' ? 48 : 32
): VolumeMesh {
  return alphaOutlineMesh(profile, mask, Math.min(profile.character === 'monitor' ? 64 : 32, grid));
}
