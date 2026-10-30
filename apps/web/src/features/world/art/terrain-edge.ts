import { groundAt } from '../definition';
import { project } from '../geometry';
import type { Point, WorldDefinition } from '../types';

/** Small irregular verges baked into path cells, never an extra live layer. */
export function paintPathVerge(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  x: number,
  y: number,
  origin: Point
): void {
  const edges = [
    { dx: 0, dy: -1, a: { x: 0, y: 0.025 }, b: { x: 1, y: 0.025 } },
    { dx: 1, dy: 0, a: { x: 0.975, y: 0 }, b: { x: 0.975, y: 1 } },
    { dx: 0, dy: 1, a: { x: 0, y: 0.975 }, b: { x: 1, y: 0.975 } },
    { dx: -1, dy: 0, a: { x: 0.025, y: 0 }, b: { x: 0.025, y: 1 } },
  ];
  c.save();
  c.strokeStyle = '#98a086';
  c.lineWidth = 1.2;
  for (const edge of edges) {
    const nx = x + edge.dx,
      ny = y + edge.dy;
    if (
      nx < 0 ||
      ny < 0 ||
      nx >= world.width ||
      ny >= world.height ||
      groundAt(world, nx, ny) !== 'grass'
    )
      continue;
    const a = project(edge.a),
      b = project(edge.b);
    c.beginPath();
    c.moveTo(origin.x + a.x, origin.y + a.y);
    c.lineTo(origin.x + b.x, origin.y + b.y);
    c.stroke();
    c.fillStyle = '#84996b';
    for (let i = 0; i < 3; i++) {
      const t = (i + 0.25 + ((x + y) % 3) * 0.2) / 3;
      c.fillRect(origin.x + a.x + (b.x - a.x) * t, origin.y + a.y + (b.y - a.y) * t, 1.4, 0.7);
    }
  }
  c.restore();
}
