/** One owner/transport generation, one pending intent, authoritative boards only. */
import type { WorldView } from './protocol';
import type { LinkStatus } from './shared-link';
import { WORLD } from './definition';
import { compileGameCabinets, type CabinetId } from './game-catalogue';
import type {
  CabinetView,
  GameAction,
  GameDelivery,
  GameIntent,
  GameMove,
  GameOutcome,
  GameView,
  GameWaiting,
} from './game-protocol';

export const GAME_COMMAND_TIMEOUT_MS = 5000;
const CABINETS = compileGameCabinets(WORLD);
export interface GamePort {
  active(): boolean;
  send(intent: GameIntent): GameDelivery | null;
}
export interface GameAttachment {
  receive(view: WorldView, stream: number, now?: number): void;
  suspend(status: LinkStatus): void;
  dispose(): void;
}
interface Pending {
  intent: GameIntent;
  delivery: GameDelivery;
  startedAt: number;
  uncertain: boolean;
}
interface GameGeneration {
  readonly epoch: string;
  readonly stream: number;
  readonly lifetime: number;
}
export interface GameObservation {
  readonly cabinet: CabinetId;
  readonly round_id: string | null;
  readonly revision: number;
  readonly generation: GameGeneration;
}
export interface ArcadeSnapshot {
  readonly generation: GameGeneration | null;
  readonly online: boolean;
  readonly cabinets: readonly CabinetView[];
  readonly nearby: readonly CabinetId[];
  readonly game: GameView | null;
  readonly request: GameWaiting | null;
  readonly pending: Readonly<Pending> | null;
  readonly outcome: GameOutcome | null;
}
const EMPTY: ArcadeSnapshot = Object.freeze({
  generation: null,
  online: false,
  cabinets: [],
  nearby: [],
  game: null,
  request: null,
  pending: null,
  outcome: null,
});
function observationSource(
  state: ArcadeSnapshot,
  cabinet: CabinetId
): GameView | GameWaiting | CabinetView | undefined {
  if (state.game?.cabinet === cabinet) return state.game;
  if (state.request?.cabinet === cabinet) return state.request;
  return state.cabinets.find(item => item.cabinet === cabinet);
}
/** Capture the rendered choice: a newer unseen requester or round cannot inherit this consent. */
export function observeGame(state: ArcadeSnapshot, cabinet: CabinetId): GameObservation | null {
  const source = observationSource(state, cabinet);
  return source && state.generation
    ? {
        cabinet,
        round_id: source.round_id,
        revision: source.revision,
        generation: state.generation,
      }
    : null;
}
interface ActionContext {
  cabinet: CabinetId;
  game: GameView | null;
  request: GameWaiting | null;
  hint: CabinetView | undefined;
  move: GameMove | undefined;
}
const own = (context: ActionContext) =>
  context.game?.cabinet === context.cabinet ? context.game : null;
const pendingInvitation = (context: ActionContext) =>
  !!own(context)?.pending && !own(context)?.paused;
const canStart = (context: ActionContext) =>
  !context.game && !context.request && context.hint?.availability === 'empty';
const ACTIONS: Readonly<Record<GameAction, (context: ActionContext) => boolean>> = {
  wait: canStart,
  start_computer: context =>
    canStart(context) ||
    (own(context)?.phase === 'waiting' && !own(context)?.pending && !own(context)?.paused),
  request: context =>
    !context.game && !context.request && context.hint?.availability === 'joinable',
  accept: pendingInvitation,
  decline: pendingInvitation,
  move: context =>
    !!context.move &&
    !!own(context)?.legal_moves.some(move => JSON.stringify(move) === JSON.stringify(context.move)),
  // The server keeps a finished table rejoinable while its result is displayed: a rotated
  // controller resumes there, then chooses a rematch.
  rejoin: context => own(context)?.needs_rejoin === true,
  rematch: context =>
    own(context)?.phase === 'finished' &&
    (own(context)?.computer === true || own(context)?.players.length === 2),
  leave: context => own(context) !== null || context.request?.cabinet === context.cabinet,
};

function stable<T>(previous: T, next: T): T {
  return JSON.stringify(previous) === JSON.stringify(next) ? previous : next;
}
function activeFrame(view: WorldView): boolean {
  return view.status === 'active' && view.controlling && view.you !== null;
}
function suspendedAction(game: GameView | null, action: GameAction): boolean {
  if (action === 'rejoin' || action === 'leave') return false;
  return game !== null && (game.paused || game.needs_rejoin);
}
function operationId(): string | null {
  const crypto = globalThis.crypto;
  if (!crypto) return null;
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class WorldGameClient {
  private state = EMPTY;
  private port: GamePort | null = null;
  private binding = 0;
  private listeners = new Set<() => void>();
  private epoch: string | null = null;
  private stream = -1;
  private revision = -1;
  private acknowledgedSeq = 0;
  private commandTimer: ReturnType<typeof setTimeout> | undefined;
  private serverAt = 0;
  private receivedAt = 0;
  private closing: { cabinet: CabinetId; round: string | null; stream: number } | null = null;
  private lastLeave: string | null = null;
  getSnapshot = (): ArcadeSnapshot => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  attach(port: GamePort): GameAttachment {
    const binding = ++this.binding;
    this.port = port;
    this.reset();
    const owned = () => this.binding === binding;
    return {
      receive: (view, stream, now) => {
        if (owned()) this.receive(view, stream, now);
      },
      suspend: status => {
        if (owned()) this.suspend(status);
      },
      dispose: () => {
        if (!owned()) return;
        this.binding++;
        this.port = null;
        this.reset();
      },
    };
  }
  private publish(next: ArcadeSnapshot): void {
    if (
      Object.keys(next).every(
        key => next[key as keyof ArcadeSnapshot] === this.state[key as keyof ArcadeSnapshot]
      )
    )
      return;
    const pendingChanged = this.state.pending !== next.pending;
    this.state = next;
    if (pendingChanged) this.scheduleDeadline(next.pending);
    this.listeners.forEach(listener => listener());
  }
  private scheduleDeadline(pending: Readonly<Pending> | null): void {
    clearTimeout(this.commandTimer);
    this.commandTimer = undefined;
    if (!pending || pending.uncertain) return;
    this.commandTimer = setTimeout(() => {
      if (this.state.pending?.intent.action_id !== pending.intent.action_id) return;
      this.tick(Math.max(performance.now(), pending.startedAt + GAME_COMMAND_TIMEOUT_MS));
    }, GAME_COMMAND_TIMEOUT_MS);
  }
  private reset(): void {
    this.epoch = null;
    this.stream = this.revision = -1;
    this.acknowledgedSeq = 0;
    this.closing = null;
    this.lastLeave = null;
    this.publish(EMPTY);
  }
  available(): boolean {
    return this.state.online && this.port?.active() === true && this.state.cabinets.length > 0;
  }
  canOpen(cabinet: CabinetId): boolean {
    return this.available() && this.state.cabinets.some(hint => hint.cabinet === cabinet);
  }
  serverTime(now = performance.now()): number | null {
    return this.epoch ? this.serverAt + Math.max(0, now - this.receivedAt) / 1000 : null;
  }
  private oldFrame(view: WorldView, stream: number): boolean {
    if (stream < this.stream) return true;
    if (stream !== this.stream || view.epoch !== this.epoch) return false;
    if (view.revision < this.revision) return true;
    return (
      !!view.game &&
      view.game.round_id === this.state.game?.round_id &&
      view.game.revision < this.state.game.revision
    );
  }
  private receive(view: WorldView, stream: number, now = performance.now()): void {
    if (!this.port || this.oldFrame(view, stream)) return;
    const changed = this.updateGeneration(view, stream, now);
    if (!activeFrame(view)) {
      this.closing = null;
      this.lastLeave = null;
      this.publish(EMPTY);
      return;
    }
    this.publish(this.project(view, changed));
    this.tick(now);
  }
  private updateGeneration(view: WorldView, stream: number, now: number): boolean {
    const changed = this.epoch !== view.epoch || this.stream !== stream;
    if (this.epoch !== view.epoch) this.closing = null;
    this.epoch = view.epoch;
    this.stream = stream;
    this.revision = view.revision;
    this.acknowledgedSeq = view.ack;
    this.serverAt = view.server_time;
    this.receivedAt = now;
    return changed;
  }
  private settlePending(
    view: WorldView,
    changed: boolean
  ): Pick<ArcadeSnapshot, 'pending' | 'outcome'> {
    const pending = changed ? null : this.state.pending;
    const outcome = this.receipt(view, pending);
    const departed =
      pending?.intent.action === 'leave' &&
      ![view.game, view.game_request].some(
        interaction => interaction?.cabinet === pending.intent.cabinet
      );
    if (pending?.intent.action === 'leave' && outcome && outcome.result !== 'accepted') {
      // Refusal never buys an automatic retry. A later explicit Leave is fresh consent.
      this.closing = null;
      this.lastLeave = null;
    }
    return {
      pending: outcome || departed ? null : pending,
      outcome: outcome ?? (changed ? null : this.state.outcome),
    };
  }
  private project(view: WorldView, changed: boolean): ArcadeSnapshot {
    return {
      generation: stable(
        this.state.generation,
        Object.freeze({ epoch: view.epoch, stream: this.stream, lifetime: this.binding })
      ),
      online: this.port?.active() === true,
      cabinets: stable(this.state.cabinets, view.cabinets ?? []),
      nearby: stable(this.state.nearby, this.nearby(view)),
      game: stable(this.state.game, view.game ?? null),
      request: stable(this.state.request, view.game_request ?? null),
      ...this.settlePending(view, changed),
    };
  }
  private nearby(view: WorldView): CabinetId[] {
    if (!view.you || view.you.pose) return [];
    const point = view.you.position;
    return CABINETS.filter(
      cabinet => Math.hypot(point.x - cabinet.approach.x, point.y - cabinet.approach.y) <= 1.25
    ).map(cabinet => cabinet.id);
  }
  private receipt(view: WorldView, pending: Readonly<Pending> | null): GameOutcome | null {
    if (!pending) return null;
    const receipt = view.receipts.find(
      item =>
        item.kind === 'game' &&
        item.seq === pending.delivery.seq &&
        item.outcome.action_id === pending.intent.action_id
    );
    return receipt?.kind === 'game' ? receipt.outcome : null;
  }
  private suspend(status: LinkStatus): void {
    if (status === 'online') return;
    if (status === 'connecting' || status === 'reconnecting') {
      this.publish({ ...this.state, online: false });
    } else this.reset();
  }
  canRequest(observed: GameObservation | null, action: GameAction, move?: GameMove): boolean {
    if (!observed || !this.matches(observed, action)) return false;
    const cabinet = observed.cabinet;
    if (!this.available() || this.state.pending || (this.closing && action !== 'leave'))
      return false;
    if (action !== 'leave' && !this.state.nearby.includes(cabinet)) return false;
    const game = this.state.game?.cabinet === cabinet ? this.state.game : null;
    if (suspendedAction(game, action)) return false;
    return ACTIONS[action]({
      cabinet,
      game: this.state.game,
      request: this.state.request,
      hint: this.state.cabinets.find(item => item.cabinet === cabinet),
      move,
    });
  }
  private matches(observed: GameObservation, action: GameAction): boolean {
    const current = observeGame(this.state, observed.cabinet);
    if (
      !current ||
      observed.generation !== current.generation ||
      observed.round_id !== current.round_id
    )
      return false;
    return action === 'leave' || observed.revision === current.revision;
  }
  request(
    observed: GameObservation | null,
    action: GameAction,
    move?: GameMove,
    now = performance.now()
  ): boolean {
    if (
      !observed ||
      !this.canRequest(observed, action, move) ||
      (action === 'move') !== (move !== undefined)
    )
      return false;
    const id = operationId();
    if (!id) return false;
    const base = {
      cabinet: observed.cabinet,
      action_id: id,
      round_id: observed.round_id,
      expected_revision: observed.revision,
    };
    let intent: GameIntent;
    if (action === 'move') {
      if (!move) return false;
      intent = { ...base, action, move };
    } else intent = { ...base, action };
    const delivery = this.port?.send(intent);
    if (!delivery) return false;
    this.publish({
      ...this.state,
      outcome: null,
      pending: { intent, delivery, startedAt: now, uncertain: false },
    });
    return true;
  }
  private ownedAt(cabinet: CabinetId): GameView | GameWaiting | null {
    if (this.state.game?.cabinet === cabinet) return this.state.game;
    return this.state.request?.cabinet === cabinet ? this.state.request : null;
  }
  tick(now = performance.now()): void {
    const pending = this.state.pending;
    if (pending && !pending.uncertain && now - pending.startedAt >= GAME_COMMAND_TIMEOUT_MS)
      this.publish({ ...this.state, pending: { ...pending, uncertain: true } });
    this.flushClose(now);
  }
  resynchronize(): void {
    this.publish({ ...this.state, pending: null, outcome: null });
  }
  close(cabinet: CabinetId, now = performance.now()): void {
    if (!this.closing)
      this.closing = {
        cabinet,
        round: observationSource(this.state, cabinet)?.round_id ?? null,
        stream: this.stream,
      };
    this.flushClose(now);
  }
  private flushClose(now: number): void {
    const closing = this.closing;
    if (!closing || !this.available() || this.awaitingCloseProcessing()) return;
    const owned = this.ownedAt(closing.cabinet);
    if (!owned || (closing.stream !== this.stream && closing.round !== owned.round_id)) {
      this.closing = null;
      this.lastLeave = null;
      return;
    }
    if (this.lastLeave === owned.round_id) return;
    this.resynchronize();
    if (this.request(observeGame(this.state, closing.cabinet), 'leave', undefined, now))
      this.lastLeave = owned.round_id;
  }
  private awaitingCloseProcessing(): boolean {
    const pending = this.state.pending;
    // A timeout alone cannot tell whether acceptance created a new round.
    // Only an exact receipt or a current server acknowledgement settles that race.
    return pending !== null && (!pending.uncertain || this.acknowledgedSeq < pending.delivery.seq);
  }
}
