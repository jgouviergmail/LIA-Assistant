import type { Point, WorldDefinition } from './types';
import { simplifyRoute } from './route-smoothing';
export interface Navigation {
  width: number;
  height: number;
  blocked: Uint8Array;
}
export const ACTOR_RADIUS = 0.22;
export function compileNavigation(world: WorldDefinition): Navigation {
  const blocked = new Uint8Array(world.width * world.height);
  const nav = { width: world.width, height: world.height, blocked };
  for (const prop of world.props) {
    if (!prop.blocking) continue;
    for (let y = Math.floor(prop.y); y < Math.ceil(prop.y + prop.depth); y++) {
      for (let x = Math.floor(prop.x); x < Math.ceil(prop.x + prop.width); x++) {
        if (x >= 0 && y >= 0 && x < world.width && y < world.height)
          blocked[y * world.width + x] = 1;
      }
    }
  }
  for (const patch of world.grounds) {
    if (patch.kind !== 'water') continue;
    for (let y = patch.y; y < patch.y + patch.height; y++) {
      for (let x = patch.x; x < patch.x + patch.width; x++) blocked[y * world.width + x] = 1;
    }
  }
  return nav;
}
export function isWalkable(nav: Navigation, p: Point): boolean {
  if (!Number.isFinite(p.x + p.y) || p.x < 0 || p.y < 0 || p.x >= nav.width || p.y >= nav.height)
    return false;
  return nav.blocked[Math.floor(p.y) * nav.width + Math.floor(p.x)] === 0;
}
function fits(nav: Navigation, p: Point): boolean {
  return [-ACTOR_RADIUS, ACTOR_RADIUS].every(dx =>
    [-ACTOR_RADIUS, ACTOR_RADIUS].every(dy => isWalkable(nav, { x: p.x + dx, y: p.y + dy }))
  );
}
export function moveActor(nav: Navigation, from: Point, delta: Point): Point {
  if (!Number.isFinite(delta.x + delta.y)) return { ...from };
  const length = Math.hypot(delta.x, delta.y);
  const scale = length > 4 ? 4 / length : 1;
  const steps = Math.max(1, Math.ceil(Math.min(length, 4) / 0.12));
  const dx = (delta.x * scale) / steps,
    dy = (delta.y * scale) / steps;
  const p = { ...from };
  for (let i = 0; i < steps; i++) {
    if (fits(nav, { x: p.x + dx, y: p.y })) p.x += dx;
    if (fits(nav, { x: p.x, y: p.y + dy })) p.y += dy;
  }
  return p;
}
/** Bounded breadth-first grid search: at most one visit per cell, no corner cutting. */
export function findRoute(
  nav: Navigation,
  from: Point,
  to: Point,
  budget = nav.width * nav.height
): Point[] {
  if (!fits(nav, from) || !fits(nav, to)) return [];
  const start = Math.floor(from.y) * nav.width + Math.floor(from.x);
  const goal = Math.floor(to.y) * nav.width + Math.floor(to.x);
  const parent = new Int32Array(nav.blocked.length).fill(-1);
  const queue = new Int32Array(nav.blocked.length);
  let head = 0,
    tail = 1;
  queue[0] = start;
  parent[start] = start;
  while (head < tail && head < budget) {
    const current = queue[head++];
    if (current === goal)
      return simplifyRoute(
        nav,
        from,
        reconstruct(parent, start, goal, nav.width, to),
        ACTOR_RADIUS
      );
    const x = current % nav.width,
      y = Math.floor(current / nav.width);
    for (const next of [
      { x: x + 1, y },
      { x: x - 1, y },
      { x, y: y + 1 },
      { x, y: y - 1 },
    ]) {
      if (!isWalkable(nav, next)) continue;
      const id = next.y * nav.width + next.x;
      if (parent[id] !== -1) continue;
      parent[id] = current;
      queue[tail++] = id;
    }
  }
  return [];
}
function reconstruct(
  parent: Int32Array,
  start: number,
  goal: number,
  width: number,
  to: Point
): Point[] {
  const route: Point[] = [{ ...to }];
  let current = goal;
  while (current !== start) {
    route.push({ x: (current % width) + 0.5, y: Math.floor(current / width) + 0.5 });
    current = parent[current];
  }
  if (goal !== start) route.push({ x: (start % width) + 0.5, y: Math.floor(start / width) + 0.5 });
  return route.reverse();
}
export function nearbyWalkable(nav: Navigation, target: Point): Point | null {
  if (fits(nav, target)) return { ...target };
  for (let radius = 0; radius <= 3; radius++) {
    for (let y = -radius; y <= radius; y++) {
      for (let x = -radius; x <= radius; x++) {
        const point = { x: Math.floor(target.x) + x + 0.5, y: Math.floor(target.y) + y + 0.5 };
        if (fits(nav, point)) return point;
      }
    }
  }
  return null;
}
