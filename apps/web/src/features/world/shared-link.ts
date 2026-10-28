/** Owns exactly one socket generation. Tickets/controller tokens live in memory only. */
import { ApiError } from '@/lib/api-client';
import { parseWorldFrame, WorldProtocolMismatch, type WorldView } from './protocol';
import type { Point } from './types';
import type { MailboxScope } from './message-protocol';
import { EMOTE_SECONDS, type EmoteKind, type EmoteRefusal } from './emote-catalogue';
import type { GameDelivery, GameIntent } from './game-protocol';
import { FRESH_SNAPSHOT_MS } from './movement';

export type LinkStatus =
  | 'connecting'
  | 'reconnecting'
  | 'online'
  | 'ended'
  | 'unavailable'
  | 'outdated';
interface Options {
  url: string;
  scene: string;
  ticket(signal: AbortSignal): Promise<string>;
  onStatus(status: LinkStatus): void;
  onView?(view: WorldView): void;
}
const RETRIES = [500, 1000, 2000, 4000];
/** Close codes the server ends a session with; every other close is a bounded retry. */
const UPGRADE_REQUIRED = 4426;
const ENDED = new Set([1000, 4401]);

export class WorldLink {
  private running = false;
  private generation = 0;
  private attempt = 0;
  private socket: WebSocket | null = null;
  private abort: AbortController | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private resume: string | null = null;
  private ready = false;
  private seq = 0;
  private openedAt = 0;
  private receivedAt = 0;
  private heartbeatAt = 0;
  private activityAt = -Infinity;
  private emoteAt = -Infinity;
  private current: WorldView | null = null;
  stream = 0;

  constructor(private options: Options) {}
  get view(): WorldView | null {
    return this.current;
  }
  get fresh(): boolean {
    return (
      this.ready && this.current !== null && performance.now() - this.receivedAt < FRESH_SNAPSHOT_MS
    );
  }
  get serverTime(): number | null {
    return this.current
      ? this.current.server_time + Math.max(0, performance.now() - this.receivedAt) / 1000
      : null;
  }
  get canMove(): boolean {
    return this.fresh && this.current?.status === 'active' && this.current.controlling;
  }
  mailboxScope(): MailboxScope | null {
    return this.canMove && this.resume && this.current && this.socket?.readyState === WebSocket.OPEN
      ? { epoch: this.current.epoch, controller: this.resume }
      : null;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.attempt = 0;
    this.watchdog = setInterval(() => this.watch(), 500);
    document.addEventListener('visibilitychange', this.visibility);
    void this.connect();
  }
  private async connect(): Promise<void> {
    const generation = ++this.generation;
    this.openedAt = performance.now();
    this.abort = new AbortController();
    this.options.onStatus(this.attempt ? 'reconnecting' : 'connecting');
    try {
      const ticket = await this.options.ticket(this.abort.signal);
      if (!this.running || generation !== this.generation) return;
      const socket = new WebSocket(this.options.url);
      this.socket = socket;
      const owned = () => this.running && generation === this.generation;
      socket.addEventListener(
        'open',
        () => {
          if (owned())
            socket.send(
              JSON.stringify({
                type: 'authenticate',
                version: 2,
                scene: this.options.scene,
                ticket,
                resume: this.resume,
              })
            );
        },
        { once: true }
      );
      socket.addEventListener('message', event => {
        if (owned()) this.receive(event.data);
      });
      socket.addEventListener(
        'close',
        event => {
          if (owned()) this.closed(event.code);
        },
        { once: true }
      );
      socket.addEventListener(
        'error',
        () => {
          // Browser errors carry no reliable HTTP verdict; recovery stays bounded.
          if (owned()) this.closed(1013);
        },
        { once: true }
      );
    } catch (error) {
      if (!this.running || generation !== this.generation) return;
      if (error instanceof ApiError && [401, 403].includes(error.status)) this.finish('ended');
      else this.closed(1013);
    }
  }
  private receive(data: unknown): void {
    try {
      if (typeof data !== 'string') throw new Error('world_text_required');
      const frame = parseWorldFrame(data);
      if (frame.type === 'ready') {
        if (this.ready) throw new Error('world_duplicate_ready');
        if (frame.scene !== this.options.scene) {
          this.finish('outdated');
          return;
        }
        this.ready = true;
        this.resume = frame.resume;
        this.seq = 0;
        this.stream++;
      } else {
        if (!this.ready) throw new Error('world_not_authenticated');
        if (this.current?.epoch === frame.epoch && this.current.revision > frame.revision) return;
        this.current = frame;
        this.receivedAt = performance.now();
        this.attempt = 0;
        this.options.onView?.(frame);
        this.options.onStatus('online');
      }
    } catch (error) {
      // Validation errors may embed private data; do not retain/log them.
      this.finish(error instanceof WorldProtocolMismatch ? 'outdated' : 'unavailable');
    }
  }
  private closed(code: number): void {
    this.disconnect();
    // Only an explicit protocol upgrade asks for a reload. A refused frame (1008)
    // or a server integrity failure (1011) is transient, like a lost transport.
    if (code === UPGRADE_REQUIRED) {
      this.finish('outdated');
      return;
    }
    if (ENDED.has(code)) {
      this.finish('ended');
      return;
    }
    const delay = RETRIES[this.attempt++];
    if (delay === undefined) {
      this.finish('unavailable');
      return;
    }
    this.options.onStatus('reconnecting');
    this.retry = setTimeout(() => {
      this.retry = null;
      if (this.running) void this.connect();
    }, delay);
  }
  private watch(): void {
    if (this.retry || !this.running) return;
    const now = performance.now();
    const since = this.ready && this.current ? this.receivedAt : this.openedAt;
    if (now - since >= 5000) {
      this.abort?.abort();
      this.closed(1013);
      return;
    }
    if (this.fresh && now - this.heartbeatAt >= 10000) this.heartbeat();
  }
  private visibility = () => {
    if (this.fresh) this.heartbeat();
  };
  private heartbeat(): void {
    this.heartbeatAt = performance.now();
    this.send({ type: 'heartbeat', visible: !document.hidden, active: false });
  }
  private send(command: Record<string, unknown>): boolean {
    if (!this.fresh || this.socket?.readyState !== WebSocket.OPEN || !this.current) return false;
    if (this.socket.bufferedAmount > 16384) {
      this.closed(1013);
      return false;
    }
    try {
      this.socket.send(JSON.stringify({ version: 2, epoch: this.current.epoch, ...command }));
      return true;
    } catch {
      this.closed(1013);
      return false;
    }
  }
  motion(direction: Point, running = false): number | null {
    if (!this.canMove || !Number.isFinite(direction.x + direction.y) || this.seq >= 2 ** 31 - 1)
      return null;
    const length = Math.max(1, Math.hypot(direction.x, direction.y));
    const seq = this.seq + 1;
    if (
      !this.send({
        type: 'move',
        seq,
        dx: direction.x / length,
        dy: direction.y / length,
        ...(running ? { running: true } : {}),
      })
    )
      return null;
    this.seq = seq;
    return seq;
  }
  pose(slot: string | null): number | null {
    if (!this.canMove || this.seq >= 2 ** 31 - 1) return null;
    const seq = this.seq + 1;
    if (!this.send({ type: 'pose', seq, slot })) return null;
    this.seq = seq;
    return seq;
  }
  game(intent: GameIntent): GameDelivery | null {
    const view = this.current;
    if (!view || !this.canMove || this.seq >= 2 ** 31 - 1) return null;
    if (document.hidden && intent.action !== 'leave') return null;
    const seq = this.seq + 1;
    if (!this.send({ type: 'game', seq, ...intent })) return null;
    this.seq = seq;
    return { seq, epoch: view.epoch, stream: this.stream };
  }
  control(type: 'accept' | 'takeover' | 'leave'): void {
    this.send({ type });
  }
  /** The sent sequence, or why nothing was sent. Taps inside the server's own
   *  gesture interval stay local, so a burst never spends the frame budget. */
  emote(emote: EmoteKind): number | EmoteRefusal {
    if (!this.canMove || document.hidden || this.seq >= 2 ** 31 - 1) return 'unavailable';
    const now = performance.now();
    if (now - this.emoteAt < EMOTE_SECONDS * 1000) return 'rate_limited';
    const seq = this.seq + 1;
    if (!this.send({ type: 'emote', seq, emote })) return 'unavailable';
    this.seq = seq;
    this.emoteAt = now;
    return seq;
  }
  activity(): void {
    const now = performance.now();
    if (!this.canMove || document.hidden || now - this.activityAt < 1000) return;
    this.activityAt = now;
    this.send({ type: 'heartbeat', visible: true, active: true });
  }
  private disconnect(): void {
    this.generation++;
    this.ready = false;
    this.current = null;
    this.abort?.abort();
    this.abort = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }
  private finish(status: LinkStatus): void {
    this.stop();
    this.options.onStatus(status);
  }
  stop(): void {
    this.running = false;
    if (this.retry) clearTimeout(this.retry);
    if (this.watchdog) clearInterval(this.watchdog);
    this.retry = null;
    this.watchdog = null;
    document.removeEventListener('visibilitychange', this.visibility);
    this.disconnect();
    this.resume = null;
  }
}
