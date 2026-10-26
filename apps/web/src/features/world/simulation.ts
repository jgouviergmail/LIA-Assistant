import { MOVEMENT } from './movement';
import type { Actor, Point, Visitor, WorldDefinition, ZoneId } from './types';
import { facingFromMotion, headingFromMotion } from './art/actor-direction';
import {
  compileNavigation,
  findRoute,
  moveActor,
  nearbyWalkable,
  type Navigation,
} from './navigation';
export interface Simulation {
  world: WorldDefinition;
  navigation: Navigation;
  player: Actor;
  visitors: Visitor[];
  bip: Actor;
  bipFollowing: boolean;
  noticeFollowing?: boolean;
  patrolIndex: number;
  wait: number;
  time: number;
}
const SPEED = MOVEMENT.walk;
const idle: Point = { x: 0, y: 0 };
function actor(position: Point): Actor {
  return { position: { ...position }, path: [], walking: false, phase: 0, facing: 0 };
}
export function createSimulation(world: WorldDefinition): Simulation {
  return {
    world,
    navigation: compileNavigation(world),
    player: actor(world.spawn),
    visitors: [],
    bip: actor(world.bipSpawn),
    bipFollowing: false,
    patrolIndex: 0,
    wait: 1.5,
    time: 0,
  };
}
export function directionFromScreen(direction: Point): Point {
  // Combined keys follow the projected floor axes, not a screen-space 45-degree ray.
  const vertical = direction.y * (direction.x === 0 ? 2 : 1);
  const p = { x: direction.x + vertical, y: vertical - direction.x };
  const n = Math.hypot(p.x, p.y);
  return n ? { x: p.x / n, y: p.y / n } : { ...idle };
}
function move(sim: Simulation, value: Actor, dt: number, input: Point, speed: number): void {
  if (value.pose) {
    value.walking = false;
    return;
  }
  const before = value.position;
  const n = Math.hypot(input.x, input.y);
  if (n) {
    value.path = [];
    value.position = moveActor(sim.navigation, before, {
      x: (input.x / n) * speed * dt,
      y: (input.y / n) * speed * dt,
    });
  } else followPath(value, speed * dt);
  const dx = value.position.x - before.x,
    dy = value.position.y - before.y;
  value.walking = Math.hypot(dx, dy) > 0.0001;
  if (value.walking) {
    value.heading = headingFromMotion({ x: dx, y: dy }, value.heading ?? value.facing * 2);
    value.facing = facingFromMotion({ x: dx, y: dy });
    value.phase += (Math.hypot(dx, dy) * 8) / 1.8;
  }
}
function followPath(value: Actor, distance: number): void {
  let remaining = distance;
  for (let limit = 0; limit < 8 && value.path.length && remaining > 0; limit++) {
    const target = value.path[0];
    const dx = target.x - value.position.x,
      dy = target.y - value.position.y;
    const length = Math.hypot(dx, dy);
    if (length <= remaining) {
      value.position = { ...target };
      value.path.shift();
      remaining -= length;
    } else {
      value.position = {
        x: value.position.x + (dx / length) * remaining,
        y: value.position.y + (dy / length) * remaining,
      };
      remaining = 0;
    }
  }
}
export function walkTo(sim: Simulation, destination: Point, running = false): boolean {
  const route = findRoute(sim.navigation, sim.player.position, destination);
  if (!route.length) return false;
  sim.player.path = route;
  sim.player.running = running;
  return true;
}
export function callBip(sim: Simulation): void {
  sim.bipFollowing = !sim.bipFollowing;
  sim.wait = 0;
  sim.bip.path = [];
}
function directBip(sim: Simulation, dt: number): void {
  if (sim.bip.path.length) return;
  sim.wait -= dt;
  if (sim.wait > 0) return;
  const following = sim.bipFollowing || sim.noticeFollowing;
  sim.wait = following ? 0.8 : 3.5;
  // A screen-side offset keeps both silhouettes and name tags readable in isometry.
  const near = { x: sim.player.position.x + 1.2, y: sim.player.position.y - 1.2 };
  const target = following
    ? nearbyWalkable(sim.navigation, near)
    : sim.world.patrol[sim.patrolIndex++ % sim.world.patrol.length];
  if (target) sim.bip.path = findRoute(sim.navigation, sim.bip.position, target);
}
export function stepSimulation(sim: Simulation, elapsed: number, input: Point): void {
  if (!Number.isFinite(elapsed) || elapsed <= 0 || !Number.isFinite(input.x + input.y)) return;
  const dt = Math.min(elapsed, 0.1);
  sim.time += dt;
  if (Math.hypot(input.x, input.y)) sim.player.running = false;
  move(sim, sim.player, dt, input, sim.player.running ? MOVEMENT.run : SPEED);
  if (!sim.player.path.length) sim.player.running = false;
  directBip(sim, dt);
  move(sim, sim.bip, dt, idle, SPEED * 0.8);
  if ((sim.bipFollowing || sim.noticeFollowing) && !sim.bip.walking) {
    sim.bip.facing = facingFromMotion({
      x: sim.player.position.x - sim.bip.position.x,
      y: sim.player.position.y - sim.bip.position.y,
    });
  }
}
export function currentZone(sim: Simulation): ZoneId {
  return zoneAt(sim.world, sim.player.position);
}
export function zoneAt(world: WorldDefinition, p: Point): ZoneId {
  return (
    world.zones.find(
      zone =>
        p.x >= zone.x && p.y >= zone.y && p.x < zone.x + zone.width && p.y < zone.y + zone.height
    )?.id ?? 'arrival'
  );
}
