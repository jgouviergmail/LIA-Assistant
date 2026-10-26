import type { Point, Size } from './types';

/** Inverse of the minimap's isometric transform, normalized to its rectangle. */
export function mapPoint(point: Point, world: Size): Point {
  const span = world.width + world.height;
  const px = point.x * (span + 8) - world.height - 4;
  const py = point.y * (span / 2 + 8) - 4;
  return {
    x: Math.max(0, Math.min(world.width, (px + py * 2) / 2)),
    y: Math.max(0, Math.min(world.height, (py * 2 - px) / 2)),
  };
}
