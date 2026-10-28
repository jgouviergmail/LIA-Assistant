/** Walking and confirmed poses precede owner-local reactions. No timer or network owner. */
import { objectApproaches, type SceneHost, type SceneTarget } from './scene-interactions';
import { compilePoseSlots, type PoseSlot } from './pose-slots';
import type { CosmeticTarget, CosmeticActionId } from './cosmetic-interactions';
import type { Simulation } from './simulation';
import type { Point } from './types';
import { cosmeticDuration } from './cosmetic-effects';
import { FOUNTAIN_IMPACT, FISHING_IMPACT, WORKOUT_CUES } from './decor-presentation';
const TIMED_CUES: Partial<Record<CosmeticActionId, readonly number[]>> = {
  workout: WORKOUT_CUES,
  fountain: [FOUNTAIN_IMPACT],
  pond: [FISHING_IMPACT],
};

interface Options {
  parent?: SceneHost;
  networked: boolean;
  target(id: string): CosmeticTarget | null;
  activate(id: string): boolean;
  cancel(id: string): void;
  cue(action: CosmeticActionId, current: () => boolean, targetId: string): void;
}
interface Reaction {
  id: string;
  action: CosmeticActionId;
  started: number;
  until: number;
  cue: number;
  slot?: PoseSlot;
}
export class CosmeticController implements SceneHost {
  private waiting: { id: string; slot: PoseSlot; until: number } | null = null;
  private reaction: Reaction | null = null;
  private slots: readonly PoseSlot[];
  constructor(
    private sim: Simulation,
    private options: Options
  ) {
    this.slots = compilePoseSlots(sim.world);
  }
  /** The parent authority's momentary silence; an unnetworked scene is always ready. */
  ready(): boolean {
    return this.options.parent?.ready?.() ?? true;
  }
  canOpen(target: SceneTarget): boolean {
    if (target.kind !== 'object')
      return this.options.parent?.canOpen(target) ?? this.localPose(target);
    const decor = this.options.target(target.id);
    if (!decor) return this.options.parent?.canOpen(target) ?? false;
    if (decor.action !== 'workout') return true;
    const slot = this.slots.find(item => item.prop === target.id);
    return (
      !!slot &&
      (this.options.parent?.canOpen({ kind: 'pose', id: slot.id, action: 'lie' }) ??
        !this.options.networked)
    );
  }
  private localPose(target: SceneTarget): boolean {
    return (
      !this.options.networked &&
      (target.kind === 'stand' ||
        (target.kind === 'pose' && this.slots.some(slot => slot.id === target.id)))
    );
  }
  private pose(slot: PoseSlot | null): boolean {
    const target: SceneTarget = slot
      ? { kind: 'pose', id: slot.id, action: slot.kind }
      : { kind: 'stand' };
    if (this.options.parent) return this.options.parent.open(target);
    if (this.options.networked) return false;
    const position = slot?.position ?? this.sim.player.pose?.approach;
    if (position) this.sim.player.position = { ...position };
    this.sim.player.pose = slot;
    this.sim.player.path = [];
    if (slot) {
      this.sim.player.facing = slot.facing;
      this.sim.player.heading = slot.facing * 2;
    }
    return true;
  }
  approaches(target: SceneTarget, from: Point): readonly Point[] | undefined {
    if (target.kind !== 'object') return undefined;
    const decor = this.options.target(target.id);
    if (!decor) return undefined;
    const prop = this.sim.world.props.find(item => item.id === target.id);
    if (decor.action === 'workout') {
      const slot = this.slots.find(item => item.prop === target.id);
      return slot ? [slot.approach] : [];
    }
    if (prop) return objectApproaches(prop, from);
    return [
      { x: decor.point.x + 0.8, y: decor.point.y },
      { x: decor.point.x - 0.8, y: decor.point.y },
      { x: decor.point.x, y: decor.point.y + 0.8 },
      { x: decor.point.x, y: decor.point.y - 0.8 },
    ];
  }
  open(target: SceneTarget): boolean {
    if (target.kind === 'stand') return this.pose(null);
    if (target.kind === 'pose') {
      const slot = this.slots.find(slot => slot.id === target.id);
      return slot ? this.pose(slot) : false;
    }
    if (target.kind !== 'object') return this.options.parent?.open(target) ?? false;
    const decor = this.options.target(target.id);
    if (!decor) return this.options.parent?.open(target) ?? false;
    if (!this.closeEnough(target, decor)) return false;
    if (decor.action !== 'workout') {
      this.start(decor);
      return true;
    }
    const slot = this.slots.find(item => item.prop === target.id);
    if (!slot || !this.pose(slot)) return false;
    this.waiting = { id: target.id, slot, until: this.sim.time + 5 };
    return true;
  }
  private closeEnough(target: SceneTarget, decor: CosmeticTarget): boolean {
    const points = this.approaches(target, this.sim.player.position) ?? [decor.point];
    return points.some(
      point =>
        Math.hypot(point.x - this.sim.player.position.x, point.y - this.sim.player.position.y) < 0.4
    );
  }
  private start(target: CosmeticTarget, slot?: PoseSlot): void {
    if (!this.options.activate(target.id)) {
      if (slot) this.pose(null);
      return;
    }
    const duration = cosmeticDuration(target.action) / 1000;
    this.reaction = {
      id: target.id,
      action: target.action,
      started: this.sim.time,
      until: this.sim.time + duration,
      cue: 0,
      slot,
    };
    if (!TIMED_CUES[target.action]) {
      this.emit(this.reaction);
      this.reaction.cue = 1;
    }
  }
  private emit(reaction: Reaction): void {
    this.options.cue(
      reaction.action,
      () => this.reaction === reaction && this.sim.time <= reaction.until,
      reaction.id
    );
  }
  update(): void {
    this.updateWaiting();
    this.updateReaction();
  }
  private updateWaiting(): void {
    const waiting = this.waiting;
    if (waiting) {
      if (this.sim.time > waiting.until) this.waiting = null;
      else if (this.sim.player.pose?.id === waiting.slot.id) {
        this.waiting = null;
        const target = this.options.target(waiting.id);
        if (target) this.start(target, waiting.slot);
      }
    }
  }
  private updateReaction(): void {
    const reaction = this.reaction;
    if (!reaction) return;
    if (reaction.slot && this.sim.player.pose?.id !== reaction.slot.id) {
      this.cancel();
      return;
    }
    const elapsed = this.sim.time - reaction.started;
    const duration = cosmeticDuration(reaction.action) / 1000;
    const cues = TIMED_CUES[reaction.action] ?? [];
    if (reaction.cue < cues.length && elapsed >= cues[reaction.cue] * duration) {
      this.emit(reaction);
      reaction.cue++;
    }
    if (this.sim.time < reaction.until) return;
    if (reaction.slot && !this.pose(null) && elapsed < 8) return;
    this.reaction = null;
  }
  cancel(): void {
    this.waiting = null;
    if (this.reaction && ['workout', 'fountain', 'pond'].includes(this.reaction.action))
      this.options.cancel(this.reaction.id);
    this.reaction = null;
  }
}
