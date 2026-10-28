import { MOVEMENT } from './movement';
/** Client prediction is cosmetic; only the server position authorizes interactions. */
import { WORLD } from './definition';
import { compilePoseSlots } from './pose-slots';
import { headingFromMotion } from './art/actor-direction';
import { ACTOR_RADIUS, findRoute, moveActor } from './navigation';
import { clearSegment } from './route-smoothing';
import { stepSimulation, zoneAt, type Simulation } from './simulation';
import type { PublicActor, WorldView } from './protocol';
import type { Point, Visitor } from './types';
import { EmoteTimeline } from './emote-timeline';

export interface SpatialLink {
  readonly serverTime?: number | null;
  readonly view: WorldView | null;
  readonly stream: number;
  readonly canMove: boolean;
  motion(direction: Point, running?: boolean): number | null;
}
export interface WorldDriver {
  step(sim: Simulation, dt: number, direction: Point): void;
}
interface Pending {
  seq: number;
  delta: Point;
}
const ZERO = { x: 0, y: 0 };
const SPEED = MOVEMENT.walk;
const SLOTS = new Map(compilePoseSlots(WORLD).map(slot => [slot.id, slot]));
export class WorldSynchronizer implements WorldDriver {
  private emotes = new EmoteTimeline();
  private observed: WorldView | null = null;
  private stream = 0;
  private epoch = '';
  private pending: Pending[] = [];
  private delta: Point = { ...ZERO };
  private elapsed = 0;
  private running = false;

  constructor(private link: SpatialLink) {}
  /** A pose may not overtake a locally buffered final movement packet. */
  get settled(): boolean {
    return this.pending.length === 0 && Math.hypot(this.delta.x, this.delta.y) < 1e-6;
  }
  private reset(): void {
    this.pending = [];
    this.delta = { ...ZERO };
    this.elapsed = 0;
    this.running = false;
  }
  private receive(sim: Simulation, view: WorldView): void {
    this.resetForView(sim, view);
    this.stream = this.link.stream;
    this.epoch = view.epoch;
    this.observed = view;
    this.pending = this.pending.filter(input => input.seq > view.ack);
    if (view.you) {
      if (zoneAt(WORLD, view.you.position) !== 'home')
        sim.player.emote = this.emotes.receive(
          view.you.id,
          view.you.emote,
          this.link.serverTime ?? view.server_time,
          performance.now() / 1000
        );
      sim.player.publicId = view.you.id;
      sim.player.appearance = view.you.appearance;
      sim.player.label = view.you.alias;
      const pose = view.you.pose ? (SLOTS.get(view.you.pose) ?? null) : null;
      if (pose || sim.player.pose) {
        this.reset();
        sim.player.path = [];
      }
      sim.player.pose = pose;
      if (pose) {
        sim.player.facing = pose.facing;
        sim.player.heading = pose.facing * 2;
      }
      let position = { ...view.you.position };
      for (const input of this.pending) position = moveActor(sim.navigation, position, input.delta);
      sim.player.position = moveActor(sim.navigation, position, this.delta);
      this.rebaseRoute(sim);
      if (!this.link.canMove) {
        sim.player.facing = view.you.facing;
        sim.player.walking = false;
      }
    }
    const previous = new Map(sim.visitors.map(visitor => [visitor.id, visitor]));
    sim.visitors = view.actors.map(actor => {
      const old = previous.get(actor.id);
      return {
        emote: this.emotes.receive(
          actor.id,
          actor.emote,
          this.link.serverTime ?? view.server_time,
          performance.now() / 1000
        ),
        pose: actor.pose ? (SLOTS.get(actor.pose) ?? null) : null,
        id: actor.id,
        label: actor.alias,
        appearance: actor.appearance,
        position: { ...visitorOrigin(actor, old) },
        from: { ...visitorOrigin(actor, old) },
        target: { ...actor.position },
        blend: 0,
        heading: visitorHeading(actor, old),
        facing: actor.facing,
        walking: actor.walking,
        phase: old?.phase ?? 0,
        path: [],
      } satisfies Visitor;
    });
  }
  /** Initial projection may own a new local path; replacement authority cannot inherit it. */
  private resetForView(sim: Simulation, view: WorldView): void {
    if (this.epoch && this.epoch !== view.epoch) this.emotes.clear();
    if (this.stream === this.link.stream && this.epoch === view.epoch && view.controlling) return;
    this.reset();
    if (this.observed) sim.player.path = [];
  }
  /** A correction changes the route's origin; an old segment may now cross a corner. */
  private rebaseRoute(sim: Simulation): void {
    const next = sim.player.path[0];
    const goal = sim.player.path.at(-1);
    if (!next || !goal || clearSegment(sim.navigation, sim.player.position, next, ACTOR_RADIUS))
      return;
    sim.player.path = findRoute(sim.navigation, sim.player.position, goal);
  }
  step(sim: Simulation, dt: number, direction: Point): void {
    const view = this.link.view;
    if (view && view !== this.observed) this.receive(sim, view);
    if (!this.link.canMove || this.pending.length >= 20) {
      this.reset();
      sim.player.path = [];
      if (!view) sim.visitors = [];
      stepSimulation(sim, dt, ZERO);
    } else if (sim.player.pose) this.seated(sim, dt, direction);
    else this.predict(sim, dt, direction);
    for (const visitor of sim.visitors) {
      const before = visitor.position;
      visitor.blend = Math.min(1, visitor.blend + dt / 0.1);
      visitor.position = {
        x: visitor.from.x + (visitor.target.x - visitor.from.x) * visitor.blend,
        y: visitor.from.y + (visitor.target.y - visitor.from.y) * visitor.blend,
      };
      const travelled = Math.hypot(visitor.position.x - before.x, visitor.position.y - before.y);
      visitor.walking = travelled > 0.0001;
      visitor.phase += (Math.min(travelled, MOVEMENT.run * dt) * 8) / 1.8;
    }
  }
  private seated(sim: Simulation, dt: number, direction: Point): void {
    sim.player.path = [];
    stepSimulation(sim, dt, ZERO);
    this.elapsed += dt;
    if (this.elapsed < 0.1) return;
    this.elapsed = 0;
    if (Math.hypot(direction.x, direction.y) > 0) this.link.motion(direction);
  }
  private predict(sim: Simulation, dt: number, direction: Point): void {
    const before = sim.player.position;
    this.running ||= sim.player.running === true;
    stepSimulation(sim, dt, direction);
    this.delta.x += sim.player.position.x - before.x;
    this.delta.y += sim.player.position.y - before.y;
    this.elapsed += dt;
    if (this.elapsed < 0.1 - 1e-6) return;
    const speed = this.running ? MOVEMENT.run : SPEED;
    const vector = {
      x: this.delta.x / (speed * this.elapsed),
      y: this.delta.y / (speed * this.elapsed),
    };
    // Avoid flooding the server with stationary moves; heartbeats own leases.
    if (Math.hypot(vector.x, vector.y) > 0.0001) {
      const seq = this.running ? this.link.motion(vector, true) : this.link.motion(vector);
      if (seq !== null) this.pending.push({ seq, delta: { ...this.delta } });
    }
    this.delta = { ...ZERO };
    this.elapsed = 0;
    this.running = false;
  }
}

function visitorOrigin(actor: PublicActor, old?: Visitor): Point {
  return actor.pose || old?.pose ? actor.position : (old?.position ?? actor.position);
}
function visitorHeading(actor: PublicActor, old?: Visitor): number {
  if (actor.pose || !old) return actor.facing * 2;
  return headingFromMotion(
    { x: actor.position.x - old.target.x, y: actor.position.y - old.target.y },
    old.heading ?? actor.facing * 2
  );
}
