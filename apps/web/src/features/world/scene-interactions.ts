import { SocialApproach } from './social-approach';
/** Local intent only. Native panels and the server retain data/mutation authority. */
import { compilePoseSlots, type PoseSlot } from './pose-slots';
import { findRoute } from './navigation';
import type { Simulation } from './simulation';
import type { Point, WorldProp } from './types';

export type SceneTarget =
  | { kind: 'stand' }
  | { kind: 'pose'; id: string; action: 'sit' | 'lie' }
  | { kind: 'lia' }
  | { kind: 'peer'; id: string }
  | { kind: 'object'; id: string };
export interface SceneHost {
  canOpen(target: SceneTarget): boolean;
  open(target: SceneTarget): boolean;
}
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
function approaches(prop: WorldProp, from: Point): Point[] {
  return [
    { x: prop.x + prop.width / 2, y: Math.ceil(prop.y + prop.depth) + 0.5 },
    { x: Math.ceil(prop.x + prop.width) + 0.5, y: prop.y + prop.depth / 2 },
    { x: prop.x + prop.width / 2, y: Math.floor(prop.y) - 0.5 },
    { x: Math.floor(prop.x) - 0.5, y: prop.y + prop.depth / 2 },
  ].sort((a, b) => distance(a, from) - distance(b, from));
}
export class SceneInteractions {
  private readonly slots: PoseSlot[];
  private readonly byProp = new Map<string, PoseSlot[]>();
  private readonly social: SocialApproach;
  private afterStand: { target: SceneTarget; expires: number } | null = null;
  private pending: { target: SceneTarget; goal: Point; expires: number } | null = null;
  constructor(
    private sim: Simulation,
    private host?: SceneHost
  ) {
    this.slots = compilePoseSlots(sim.world);
    for (const slot of this.slots)
      this.byProp.set(slot.prop, [...(this.byProp.get(slot.prop) ?? []), slot]);
    this.social = new SocialApproach(sim, host);
  }
  cancel(): void {
    this.social.cancel();
    this.afterStand = null;
    this.pending = null;
  }
  resolve(target: SceneTarget): SceneTarget {
    if (target.kind !== 'object') return target;
    const slots = this.byProp.get(target.id) ?? [];
    const free = slots.filter(
      slot => !this.sim.visitors.some(person => person.pose?.id === slot.id)
    );
    const slot = (free.length ? free : slots).sort(
      (a, b) =>
        distance(a.approach, this.sim.player.position) -
        distance(b.approach, this.sim.player.position)
    )[0];
    return slot ? { kind: 'pose', id: slot.id, action: slot.kind } : target;
  }
  choose(target: SceneTarget): boolean {
    this.cancel();
    if (!this.host?.canOpen(target)) return false;
    if (target.kind === 'lia' || target.kind === 'peer') return this.social.start(target);
    if (target.kind === 'stand') {
      this.sim.player.path = [];
      return this.host.open(target);
    }
    if (this.sim.player.pose) return this.standBefore(target);
    const prop =
      target.kind === 'object' ? this.sim.world.props.find(item => item.id === target.id) : null;
    const slot = target.kind === 'pose' ? this.slots.find(item => item.id === target.id) : null;
    const goals = slot ? [slot.approach] : prop ? approaches(prop, this.sim.player.position) : [];
    for (const goal of goals) {
      const route = findRoute(this.sim.navigation, this.sim.player.position, goal);
      if (!route.length) continue;
      this.sim.player.path = route;
      this.pending = { target, goal, expires: this.sim.time + 60 };
      return true;
    }
    return false;
  }
  private standBefore(target: SceneTarget): boolean {
    if (!this.host?.open({ kind: 'stand' })) return false;
    this.afterStand = { target, expires: this.sim.time + 5 };
    return true;
  }
  update(): void {
    this.social.update();
    if (this.afterStand) {
      const next = this.afterStand;
      if (this.sim.time > next.expires) this.cancel();
      else if (!this.sim.player.pose) this.choose(next.target);
      return;
    }
    const pending = this.pending;
    if (!pending) return;
    if (this.sim.time > pending.expires || !this.host?.canOpen(pending.target)) {
      this.cancel();
      this.sim.player.path = [];
      return;
    }
    if (this.sim.player.path.length || distance(this.sim.player.position, pending.goal) > 0.28)
      return;
    // Prediction may arrive before the server. Keep this bounded local intent until
    // the authoritative position is close enough; do not replay a sent request.
    if (this.host.open(pending.target)) this.cancel();
  }
  nearest(): SceneTarget | null {
    if (!this.host) return null;
    if (this.sim.player.pose) return { kind: 'stand' };
    const from = this.sim.player.position;
    const candidates: { target: SceneTarget; at: Point }[] = [
      { target: { kind: 'lia' }, at: this.sim.bip.position },
      ...this.sim.visitors.map(person => ({
        target: { kind: 'peer' as const, id: person.id },
        at: person.position,
      })),
    ];
    for (const prop of this.sim.world.props) {
      const slot = this.byProp.get(prop.id)?.[0];
      const point = slot?.approach ?? approaches(prop, from)[0];
      if (distance(from, point) <= 1.8)
        candidates.push({ target: this.resolve({ kind: 'object', id: prop.id }), at: point });
    }
    candidates.sort((a, b) => distance(a.at, from) - distance(b.at, from));
    for (const candidate of candidates) {
      if (distance(from, candidate.at) > 2.5 || !this.host.canOpen(candidate.target)) continue;
      // No nearby command through walls: the walkable path must itself be short.
      const route = findRoute(this.sim.navigation, from, candidate.at, 64);
      let previous = from,
        length = 0;
      for (const next of route) {
        length += distance(previous, next);
        previous = next;
      }
      if (route.length && length <= 2.5) return candidate.target;
    }
    return null;
  }
}
