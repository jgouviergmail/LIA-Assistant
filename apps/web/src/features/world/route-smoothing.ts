import type { Navigation } from './navigation';
import type { Point } from './types';

/** Sweep the whole body, not a few samples that can miss an obstacle corner. */
function crossesCell(from: Point, to: Point, x: number, y: number, radius: number): boolean {
  let entry = 0;
  let exit = 1;
  for (const [start, end, minimum] of [
    [from.x, to.x, x],
    [from.y, to.y, y],
  ]) {
    const delta = end - start;
    const low = minimum - radius;
    const high = minimum + 1 + radius;
    if (Math.abs(delta) < 1e-12) {
      if (start < low || start > high) return false;
      continue;
    }
    const a = (low - start) / delta;
    const b = (high - start) / delta;
    entry = Math.max(entry, Math.min(a, b));
    exit = Math.min(exit, Math.max(a, b));
    if (entry > exit) return false;
  }
  return true;
}

export function clearSegment(nav: Navigation, from: Point, to: Point, radius: number): boolean {
  const left = Math.max(0, Math.floor(Math.min(from.x, to.x) - radius));
  const top = Math.max(0, Math.floor(Math.min(from.y, to.y) - radius));
  const right = Math.min(nav.width - 1, Math.floor(Math.max(from.x, to.x) + radius));
  const bottom = Math.min(nav.height - 1, Math.floor(Math.max(from.y, to.y) + radius));
  for (let y = top; y <= bottom; y++) {
    for (let x = left; x <= right; x++) {
      if (nav.blocked[y * nav.width + x] && crossesCell(from, to, x, y, radius)) return false;
    }
  }
  return true;
}

/** Remove grid turns only when their replacement has full body clearance. */
export function simplifyRoute(
  nav: Navigation,
  from: Point,
  route: Point[],
  radius: number
): Point[] {
  const result: Point[] = [];
  for (let first = 0; first < route.length; ) {
    let next = route.length - 1;
    while (next > first && !clearSegment(nav, from, route[next], radius)) next--;
    const point = route[next];
    if (!clearSegment(nav, from, point, radius)) return [];
    if (Math.hypot(point.x - from.x, point.y - from.y) > 1e-9) result.push(point);
    from = point;
    first = next + 1;
  }
  return result.length ? result : route.slice(-1);
}
