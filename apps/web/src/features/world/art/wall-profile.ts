import type { Point } from '../types';
/** Outline of a single connected wall tile; arms meet at full tile boundaries. */
export const WALL_BODY_THICKNESS = 0.24;
export function wallProfile(mask: number, thickness: number): Point[] {
  const low = (1 - thickness) / 2,
    high = (1 + thickness) / 2;
  const grid = [0, low, high, 1];
  const cells = new Set(['1:1']);
  if (mask & 1) cells.add('2:1');
  if (mask & 2) cells.add('1:2');
  if (mask & 4) cells.add('0:1');
  if (mask & 8) cells.add('1:0');
  const edges = new Map<string, Point>();
  const key = (p: Point) => p.x + ':' + p.y;
  const add = (a: Point, b: Point) => edges.set(key(a), b);
  for (const cell of cells) {
    const [x, y] = cell.split(':').map(Number);
    const a = { x: grid[x], y: grid[y] },
      b = { x: grid[x + 1], y: grid[y] };
    const c = { x: grid[x + 1], y: grid[y + 1] },
      d = { x: grid[x], y: grid[y + 1] };
    if (!cells.has(x + ':' + (y - 1))) add(a, b);
    if (!cells.has(x + 1 + ':' + y)) add(b, c);
    if (!cells.has(x + ':' + (y + 1))) add(c, d);
    if (!cells.has(x - 1 + ':' + y)) add(d, a);
  }
  const start = edges.keys().next().value;
  if (!start) return [];
  let cursor = start;
  const result: Point[] = [];
  do {
    const [x, y] = cursor.split(':').map(Number);
    result.push({ x, y });
    const next = edges.get(cursor);
    if (!next) return [];
    cursor = key(next);
  } while (cursor !== start && result.length <= edges.size);
  return result;
}
