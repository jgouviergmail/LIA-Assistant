/** Orthographic projection of an actual sphere, in the face's em coordinates. */
import type { EyesSize } from '@/stores/eyesWidgetStore';
import type { ChannelValues } from '../rig/channels';

export const SMILEY_SPHERE_RADIUS = 1.274;
const DEGREE = Math.PI / 180;
const FONT_SIZE = { sm: 20, md: 30, lg: 44, xl: 64 } as const;

export interface SpherePoint {
  x: number;
  y: number;
}
export interface SpherePose {
  yaw: number;
  pitch: number;
}
interface Vector3 extends SpherePoint {
  z: number;
}

export function finite(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

export function spherePose(values: Readonly<ChannelValues>): SpherePose {
  return {
    yaw: Math.max(-1.3, Math.min(1.3, finite(values.headYaw))) * 16 * DEGREE,
    pitch: Math.max(-1.3, Math.min(1.3, finite(values.headPitch))) * -10 * DEGREE,
  };
}

function rotate(point: Vector3, pose: SpherePose): Vector3 {
  const sy = Math.sin(finite(pose.yaw)),
    cy = Math.cos(finite(pose.yaw));
  const sp = Math.sin(finite(pose.pitch)),
    cp = Math.cos(finite(pose.pitch));
  const x = point.x * cy + point.z * sy;
  const z = point.z * cy - point.x * sy;
  return { x, y: point.y * cp - z * sp, z: point.y * sp + z * cp };
}

/** The derivatives are surface tangents; frontal projection is exactly identity. */
export function projectSmileySurface(point: SpherePoint, pose: SpherePose) {
  return projectSurface(point, pose, SMILEY_SPHERE_RADIUS, 0.88);
}

/** The crown ornament sits just outside the body, with its own surface tangent. */
export function projectSmileyCrown(pose: SpherePose) {
  const projected = projectSurface({ x: 0, y: -1.3 }, pose, SMILEY_SPHERE_RADIUS + 0.091, 0.98);
  // A tied ornament is an upright volume, not a decal squeezed into the
  // crown's steep tangent. Its attachment rotates with the same head.
  const horizontal = rotate({ x: 1, y: 0, z: 0 }, pose);
  const vertical = rotate({ x: 0, y: 1, z: 0 }, pose);
  return { ...projected, a: horizontal.x, b: horizontal.y, c: vertical.x, d: vertical.y };
}

function projectSurface(point: SpherePoint, pose: SpherePose, radius: number, coverage: number) {
  const limit = radius * coverage;
  const x = finite(point.x),
    y = finite(point.y);
  const scale = Math.min(1, limit / (Math.hypot(x, y) || 1));
  const local = { x: x * scale, y: y * scale, z: 0 };
  local.z = Math.sqrt(radius ** 2 - local.x ** 2 - local.y ** 2);
  const position = rotate(local, pose);
  const horizontal = rotate({ x: 1, y: 0, z: -local.x / local.z }, pose);
  const vertical = rotate({ x: 0, y: 1, z: -local.y / local.z }, pose);
  return { ...position, a: horizontal.x, b: horizontal.y, c: vertical.x, d: vertical.y };
}

export function smileySphereResolution(size: EyesSize, dpr: number): number {
  const density = Number.isFinite(dpr) ? Math.max(1, Math.min(2, dpr)) : 1;
  return Math.min(192, Math.ceil(FONT_SIZE[size] * 2.6 * density));
}
