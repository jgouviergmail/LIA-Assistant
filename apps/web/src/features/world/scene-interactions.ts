import { SocialApproach } from './social-approach';
import { cabinetApproach, CABINET_GAMES } from './game-catalogue';
/** Local intent only. Native panels and the server retain data/mutation authority. */
import { compilePoseSlots, type PoseSlot } from './pose-slots';
import { findRoute } from './navigation';
import type { Simulation } from './simulation';
import type { Point, WorldProp } from './types';
import { cosmeticPropTarget } from './cosmetic-interactions';

export type SceneTarget =
  | { kind: 'stand' }
  | { kind: 'pose'; id: string; action: 'sit' | 'lie' }
  | { kind: 'lia' }
  | { kind: 'peer'; id: string }
  | { kind: 'object'; id: string };
export interface SceneHost {
  approaches?(target: SceneTarget, from: Point): readonly Point[] | undefined;
  canOpen(target: SceneTarget): boolean;
  open(target: SceneTarget): boolean;
  /**
   * False while the authority is momentarily silent (a snapshot gap): a pending
   * approach freezes instead of being withdrawn, within its own deadline.
   */
  ready?(): boolean;
}
export const SCENE_APPROACH_SECONDS = 60;
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export function objectApproaches(prop: WorldProp, from: Point): Point[] {
  if (prop.kind === 'arcade' && prop.key && Object.hasOwn(CABINET_GAMES, prop.key))
    return [cabinetApproach(prop)];
  // Grid-centred goals leave room for the actor radius. Exact geometric centres
  // can straddle a neighbouring shore rock even when the destination cell is free.
  const middleX = Math.floor(prop.x + prop.width / 2) + 0.5;
  const middleY = Math.floor(prop.y + prop.depth / 2) + 0.5;
  return [
    { x: middleX, y: Math.ceil(prop.y + prop.depth) + 0.5 },
    { x: Math.ceil(prop.x + prop.width) + 0.5, y: middleY },
    { x: middleX, y: Math.floor(prop.y) - 0.5 },
    { x: Math.floor(prop.x) - 0.5, y: middleY },
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
    const prop = this.sim.world.props.find(item => item.id === target.id);
    if (prop && cosmeticPropTarget(prop)?.action === 'workout') return target;
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
    const goals =
      this.host.approaches?.(target, this.sim.player.position) ??
      (slot ? [slot.approach] : prop ? objectApproaches(prop, this.sim.player.position) : []);
    for (const goal of goals) {
      const route = findRoute(this.sim.navigation, this.sim.player.position, goal);
      if (!route.length) continue;
      this.sim.player.path = route;
      this.pending = { target, goal, expires: this.sim.time + SCENE_APPROACH_SECONDS };
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
    // Every authority predicate is false during a snapshot gap; reading that as
    // a withdrawn target would cancel the approach the person asked for.
    const silent = this.host?.ready?.() === false;
    this.social.update();
    if (this.afterStand) this.standThenChoose(this.afterStand, silent);
    else if (this.pending && silent) this.hold(this.pending);
    else if (this.pending) this.advance(this.pending);
  }
  private standThenChoose(next: { target: SceneTarget; expires: number }, silent: boolean): void {
    if (this.sim.time > next.expires) this.cancel();
    else if (!silent && !this.sim.player.pose) this.choose(next.target);
  }
  /** The avatar holds still while the authority is silent; the deadline still runs. */
  private hold(pending: { expires: number }): void {
    this.sim.player.path = [];
    if (this.sim.time > pending.expires) this.cancel();
  }
  private advance(pending: { target: SceneTarget; goal: Point; expires: number }): void {
    if (!this.refreshGoal(pending)) return;
    if (this.sim.time > pending.expires || !this.host?.canOpen(pending.target)) {
      this.cancel();
      this.sim.player.path = [];
      return;
    }
    if (this.sim.player.path.length) return;
    if (distance(this.sim.player.position, pending.goal) > 0.28) {
      this.sim.player.path = findRoute(this.sim.navigation, this.sim.player.position, pending.goal);
      if (!this.sim.player.path.length) this.cancel();
      return;
    }
    // Prediction may arrive before the server. Keep this bounded local intent until
    // the authoritative position is close enough; do not replay a sent request.
    if (this.host.open(pending.target)) this.cancel();
  }
  private refreshGoal(pending: { target: SceneTarget; goal: Point }): boolean {
    const moving = this.host?.approaches?.(pending.target, this.sim.player.position);
    if (!moving?.length || !moving.every(point => distance(point, pending.goal) > 0.9)) return true;
    for (const goal of moving) {
      const route = findRoute(this.sim.navigation, this.sim.player.position, goal);
      if (!route.length) continue;
      pending.goal = goal;
      this.sim.player.path = route;
      return true;
    }
    this.cancel();
    this.sim.player.path = [];
    return false;
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
      const point = slot?.approach ?? objectApproaches(prop, from)[0];
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
