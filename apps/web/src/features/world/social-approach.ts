import type { SceneHost } from './scene-interactions';
/** Scene conversation intent. Proximity never grants access to private data. */
import { findRoute } from './navigation';
import type { Simulation } from './simulation';
import type { Point } from './types';
export type PersonTarget = { kind: 'lia' } | { kind: 'peer'; id: string };
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export function personPosition(sim: Simulation, target: PersonTarget): Point | null {
  return target.kind === 'lia'
    ? sim.bip.position
    : (sim.visitors.find(person => person.id === target.id)?.position ?? null);
}
export function conversationRoute(sim: Simulation, at: Point): Point[] {
  const from = sim.player.position;
  if (distance(from, at) > 2.5) return [];
  const route = findRoute(sim.navigation, from, at, 64);
  let previous = from,
    length = 0;
  for (const next of route) {
    length += distance(previous, next);
    previous = next;
  }
  return length <= 2.5 ? route : [];
}
export class SocialApproach {
  private intent: { target: PersonTarget; expires: number; nextCheck: number } | null = null;
  constructor(
    private sim: Simulation,
    private host?: SceneHost
  ) {}
  cancel(): void {
    this.intent = null;
  }
  start(target: PersonTarget): boolean {
    if (!this.host?.canOpen(target)) return false;
    const at = personPosition(this.sim, target);
    if (!at) return false;
    if (conversationRoute(this.sim, at).length) {
      this.sim.player.path = [];
      return this.host.open(target);
    }
    if (this.sim.player.pose || !this.approach(at)) return false;
    this.intent = { target, expires: this.sim.time + 30, nextCheck: this.sim.time + 0.5 };
    return true;
  }
  update(): void {
    const intent = this.intent;
    if (!intent) return;
    const at = personPosition(this.sim, intent.target);
    if (!at || this.sim.time > intent.expires || !this.host?.canOpen(intent.target)) {
      this.sim.player.path = [];
      this.cancel();
      return;
    }
    if (conversationRoute(this.sim, at).length) {
      this.sim.player.path = [];
      if (this.host.open(intent.target)) this.cancel();
      return;
    }
    if (this.sim.time < intent.nextCheck) return;
    intent.nextCheck = this.sim.time + 0.5;
    if (!this.approach(at)) {
      this.sim.player.path = [];
      this.cancel();
    }
  }
  private approach(at: Point): boolean {
    const goals = Array.from({ length: 8 }, (_, i) => ({
      x: at.x + Math.cos((i * Math.PI) / 4) * 1.4,
      y: at.y + Math.sin((i * Math.PI) / 4) * 1.4,
    })).sort(
      (a, b) => distance(a, this.sim.player.position) - distance(b, this.sim.player.position)
    );
    for (const goal of goals) {
      const route = findRoute(this.sim.navigation, this.sim.player.position, goal);
      if (!route.length) continue;
      this.sim.player.path = route;
      return true;
    }
    return false;
  }
}
