import { project } from '../geometry';
import type { Sprite } from './painter';
import type { Point, Rect, WorldDefinition } from '../types';
import { WALL_BODY_THICKNESS } from './wall-profile';
import { groundAt } from '../definition';
/** Baked chunk clipping: indoor tile edges end under the outer wall, not in the grass. */
export function floorEdgeBounds(world: WorldDefinition): Map<string, Rect> {
  const rooms = world.zones.filter(zone => zone.covered);
  const covered = (p: Point) =>
    rooms.some(r => p.x >= r.x && p.y >= r.y && p.x < r.x + r.width && p.y < r.y + r.height);
  const continuous = (p: Point) => {
    const kind = groundAt(world, p.x, p.y);
    return covered(p) || (kind !== 'grass' && kind !== 'water');
  };
  const result = new Map<string, Rect>();
  const low = (1 - WALL_BODY_THICKNESS) / 2,
    high = (1 + WALL_BODY_THICKNESS) / 2;
  for (const wall of world.props) {
    if (wall.kind !== 'partition' || !covered({ x: wall.x + 0.5, y: wall.y + 0.5 })) continue;
    const x = continuous({ x: wall.x - 0.5, y: wall.y + 0.5 }) ? 0 : low;
    const y = continuous({ x: wall.x + 0.5, y: wall.y - 0.5 }) ? 0 : low;
    const right = continuous({ x: wall.x + 1.5, y: wall.y + 0.5 }) ? 1 : high;
    const bottom = continuous({ x: wall.x + 0.5, y: wall.y + 1.5 }) ? 1 : high;
    if (x || y || right < 1 || bottom < 1)
      result.set(wall.x + ':' + wall.y, { x, y, width: right - x, height: bottom - y });
  }
  return result;
}

function drawTile(c: CanvasRenderingContext2D, sprite: Sprite, origin: Point): void {
  c.drawImage(
    sprite.canvas,
    origin.x - sprite.anchorX,
    origin.y - sprite.anchorY,
    sprite.width,
    sprite.height
  );
}
/** One-time floor chunk baking, with the grass base preserved outside its wall boundary. */
export function paintFloorCell(
  c: CanvasRenderingContext2D,
  tile: Sprite,
  origin: Point,
  crop?: Rect,
  grass?: Sprite
): void {
  if (!crop) {
    drawTile(c, tile, origin);
    return;
  }
  if (grass) drawTile(c, grass, origin);
  c.save();
  c.beginPath();
  const corners = [
    { x: crop.x, y: crop.y },
    { x: crop.x + crop.width, y: crop.y },
    { x: crop.x + crop.width, y: crop.y + crop.height },
    { x: crop.x, y: crop.y + crop.height },
  ];
  corners.forEach((corner, i) => {
    const at = project(corner);
    if (i) c.lineTo(at.x + origin.x, at.y + origin.y);
    else c.moveTo(at.x + origin.x, at.y + origin.y);
  });
  c.closePath();
  c.clip();
  drawTile(c, tile, origin);
  c.restore();
}
