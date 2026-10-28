import type { SceneHost } from './scene-interactions';
/** Scene conversation intent. Proximity never grants access to private data. */
import { findRoute, type Navigation } from './navigation';
import type { Simulation } from './simulation';
import type { Point } from './types';
export type PersonTarget = { kind: 'lia' } | { kind: 'peer'; id: string };
export const SOCIAL_APPROACH_SECONDS = 30;
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export function personPosition(sim: Simulation, target: PersonTarget): Point | null {
  return target.kind === 'lia'
    ? sim.bip.position
    : (sim.visitors.find(person => person.id === target.id)?.position ?? null);
}
export function conversationRoute(sim: Simulation, at: Point): Point[] {
  return shortConversationRoute(sim.navigation, sim.player.position, at, 2.5);
}
/** Bound conversational reach by a walkable route, never a line through a wall. */
export function shortConversationRoute(
  navigation: Navigation,
  from: Point,
  at: Point,
  maximum: number
): Point[] {
  if (distance(from, at) > maximum) return [];
  const route = findRoute(navigation, from, at, 64);
  let previous = from,
    length = 0;
  for (const next of route) {
    length += distance(previous, next);
    previous = next;
  }
  return length <= maximum ? route : [];
}
export class SocialApproach {
  private intent: { target: PersonTarget; expires: number; nextCheck: number } | null = null;
  constructor(
    private sim: Simulation,
    private host?: SceneHost
  ) {}
  cancel(): void {
    if (this.intent?.target.kind === 'lia') this.sim.bipInteractionHeld = false;
    this.intent = null;
  }
  start(target: PersonTarget): boolean {
    this.cancel();
    if (!this.host?.canOpen(target)) return false;
    const at = personPosition(this.sim, target);
    if (!at) return false;
    if (conversationRoute(this.sim, at).length) {
      this.sim.player.path = [];
      return this.host.open(target);
    }
    if (this.sim.player.pose || !this.approach(at)) return false;
    this.intent = {
      target,
      expires: this.sim.time + SOCIAL_APPROACH_SECONDS,
      nextCheck: this.sim.time + 0.5,
    };
    if (target.kind === 'lia') this.sim.bipInteractionHeld = true;
    return true;
  }
  update(): void {
    const intent = this.intent;
    if (!intent) return;
    const at = personPosition(this.sim, intent.target);
    if (!at || this.sim.time > intent.expires) {
      this.sim.player.path = [];
      this.cancel();
      return;
    }
    // A snapshot gap freezes the approach; authority back replans at once.
    if (this.host?.ready?.() === false) {
      this.sim.player.path = [];
      intent.nextCheck = this.sim.time;
      return;
    }
    if (!this.host?.canOpen(intent.target)) {
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
