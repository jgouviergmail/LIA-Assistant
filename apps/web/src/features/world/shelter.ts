/** Static shelter union shared by the personal atmosphere and weather particles. */
import type { Point, Rect, WorldDefinition } from './types';
const cache = new WeakMap<WorldDefinition['zones'], readonly Rect[]>();
export function isSheltered(world: WorldDefinition, p: Point): boolean {
  return world.zones.some(
    z => z.covered && p.x >= z.x && p.x < z.x + z.width && p.y >= z.y && p.y < z.y + z.height
  );
}
export function coveredRectangles(world: WorldDefinition): readonly Rect[] {
  const previous = cache.get(world.zones);
  if (previous) return previous;
  const zones = world.zones.filter(z => z.covered);
  const ys = [...new Set(zones.flatMap(z => [z.y, z.y + z.height]))].sort((a, b) => a - b);
  const result: Rect[] = [];
  for (let i = 0; i < ys.length - 1; i++) {
    const y = ys[i],
      height = ys[i + 1] - y;
    const spans = zones
      .filter(z => z.y <= y && z.y + z.height >= y + height)
      .map(z => ({ start: z.x, end: z.x + z.width }))
      .sort((a, b) => a.start - b.start);
    let merged: { start: number; end: number } | null = null;
    for (const span of spans) {
      if (merged && span.start <= merged.end) merged.end = Math.max(merged.end, span.end);
      else {
        if (merged) result.push({ x: merged.start, y, width: merged.end - merged.start, height });
        merged = { ...span };
      }
    }
    if (merged) result.push({ x: merged.start, y, width: merged.end - merged.start, height });
  }
  cache.set(world.zones, result);
  return result;
}
