import type { Point } from '../types';

/** World axes, independent of screen projection: +x, +y, -x, -y. */
export type Facing = 0 | 1 | 2 | 3;
interface Part extends Point {
  width: number;
  depth: number;
}

export function facingFromMotion(delta: Point): Facing {
  return Math.abs(delta.x) > Math.abs(delta.y) + 1e-9 ? (delta.x > 0 ? 0 : 2) : delta.y > 0 ? 1 : 3;
}

/** Authored parts face +y; rotate around the unit-square center. */
export function actorBox(part: Part, facing: number): Part {
  const { x, y, width, depth } = part;
  switch (facing) {
    case 0:
      return { x: y, y: 1 - x - width, width: depth, depth: width };
    case 2:
      return { x: 1 - y - depth, y: x, width: depth, depth: width };
    case 3:
      return { x: 1 - x - width, y: 1 - y - depth, width, depth };
    default:
      return part;
  }
}

export function actorFace(facing: number): { side: boolean; x: number; y: number } | null {
  if (facing === 0) return { side: true, x: 0.94, y: 0.22 };
  if (facing === 1) return { side: false, x: 0.22, y: 0.94 };
  return null;
}

/** Eight visual headings, +x first, increasing toward +y. Transport facing stays cardinal. */
export function headingFromMotion(delta: Point, previous: number): number {
  if (!Number.isFinite(delta.x + delta.y) || Math.hypot(delta.x, delta.y) < 1e-6) return previous;
  return (Math.round((Math.atan2(delta.y, delta.x) * 4) / Math.PI) + 8) % 8;
}
/** Rotate authored +y-facing geometry, never its screen-space bounding rectangle. */
export function actorPoint(point: Point, heading: number): Point {
  const angle = (heading * Math.PI) / 4 - Math.PI / 2;
  const x = point.x - 0.5,
    y = point.y - 0.5;
  return {
    x: 0.5 + x * Math.cos(angle) - y * Math.sin(angle),
    y: 0.5 + x * Math.sin(angle) + y * Math.cos(angle),
  };
}
