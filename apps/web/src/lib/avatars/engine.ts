import { sameAvatar, type AvatarDemand } from './activation-policy';
import { AvatarStartError, type AvatarApi, type AvatarStartFailure } from './api';
import type { AvatarConnectionState } from './types';
import type { SimliTransportEvents } from './simli-transport';
import type { AvatarSession } from './types';
import { SimliPlayout, pushDecoded } from './playout';
import { logger } from '@/lib/logger';

type AvatarFailureCode =
  | AvatarStartFailure
  | 'avatar_connection_timeout'
  | 'avatar_transport_failed'
  | 'avatar_transport_closed'
  | 'avatar_connect_failed'
  | 'avatar_heartbeat_failed'
  | 'avatar_output_failed';

export interface AvatarWire {
  connect(session: AvatarSession, signal: AbortSignal): Promise<void>;
  close(): void;
  skip(): void;
  sendPcm(packet: Uint8Array): boolean;
}
export interface AvatarMedia {
  readonly ready: boolean;
  readonly connected?: boolean;
  video(stream: MediaStream): void;
  audio(stream: MediaStream): void;
  reset(destroy?: boolean): void;
  mute(): void;
  unlock(): Promise<void>;
  attach(element: HTMLVideoElement | null): void;
  begin(onAudible: () => void): void;
  readonly clock: number;
  readonly quiet: boolean;
}
export interface AvatarEngineDeps {
  api: AvatarApi;
  wire(events: SimliTransportEvents): AvatarWire;
  media(changed: () => void): AvatarMedia;
}
/** One production's continuous remote stream: every decoded clip joins it, the drain is waited once. */
export interface AvatarPhrase {
  /** One decoded clip joins the phrase; resolves once accepted, never once heard. */
  feed(buffer: AudioBuffer, signal: AbortSignal): Promise<void>;
  /** The last clip was fed: drain the remote output, then mute it. */
  finish(): Promise<void>;
}

interface Connection {
  demand: AvatarDemand;
  owner: string;
  lease?: string;
  controller: AbortController;
  wire: AvatarWire | null;
  closing: boolean;
  refused?: boolean;
}

/** One mode-owned connection; phrases never mint tokens or renew leases. */
export class AvatarEngine {
  private demand: AvatarDemand | null = null;
  private connection: Connection | null = null;
  private status: AvatarConnectionState = 'off';
  private failureCode: AvatarFailureCode | null = null;
  private busy = false;
  private disposed = false;
  private permission = false;
  private preparing = false;
  private failed: AvatarDemand | null = null;
  private blocked: Connection | null = null;
  private deadline: ReturnType<typeof setTimeout> | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private renewal: ReturnType<typeof setTimeout> | null = null;
  private listeners = new Set<() => void>();
  private phrase: SimliPlayout | null = null;
  readonly media: AvatarMedia;
  constructor(readonly deps: AvatarEngineDeps) {
    this.media = deps.media(() => this.mediaChanged());
  }
  get state(): AvatarConnectionState {
    return this.status;
  }
  get failure(): AvatarFailureCode | null {
    return this.failureCode;
  }
  get present(): boolean {
    return this.demand !== null || this.preparing;
  }
  get permitted(): boolean {
    return this.permission;
  }
  setPermission(permitted: boolean, preparing = false): void {
    if (this.permission === permitted && this.preparing === preparing) return;
    this.permission = permitted;
    this.preparing = preparing;
    this.publish(this.status);
  }
  get ready(): boolean {
    return this.status === 'ready' && this.media.ready;
  }
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  snapshot = (): AvatarConnectionState => this.status;
  private publish(status: AvatarConnectionState): void {
    this.status = status;
    for (const listener of this.listeners) listener();
  }
  setDemand(demand: AvatarDemand | null): void {
    if (this.disposed) return;
    const previous = this.demand;
    this.demand = demand;
    if (demand && sameAvatar(previous, demand) && this.retain(demand, previous)) {
      return;
    }
    if (!sameAvatar(previous, demand)) this.failed = null;
    if (this.connection && !sameAvatar(this.connection.demand, demand))
      this.stopWire(this.connection);
    if (!demand) this.publish('off');
    queueMicrotask(() => void this.reconcile());
  }
  private retain(demand: AvatarDemand, previous: AvatarDemand | null): boolean {
    const connection = this.connection;
    if (!connection || connection.closing) return false;
    if (previous?.source !== demand.source || previous?.live_id !== demand.live_id) {
      this.interrupt();
      connection.demand = demand;
      void this.checkHeartbeat(connection);
    }
    return true;
  }
  private async reconcile(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      if (this.connection?.closing) await this.release(this.connection);
      const demand = this.demand;
      if (this.disposed || !demand || this.connection || sameAvatar(this.failed, demand)) return;
      if (this.blocked?.demand.credential === demand.credential) {
        this.failed = demand;
        this.publish('unavailable');
        return;
      }
      await this.open(demand);
    } finally {
      this.busy = false;
      if (
        this.connection?.closing ||
        (this.demand && !this.connection && !sameAvatar(this.failed, this.demand))
      ) {
        void this.reconcile();
      }
    }
  }
  private async open(demand: AvatarDemand): Promise<void> {
    this.failureCode = null;
    const mintedAt = performance.now();
    const connection: Connection = {
      demand,
      owner: crypto.randomUUID(),
      controller: new AbortController(),
      wire: null,
      closing: false,
    };
    this.connection = connection;
    this.publish('connecting');
    this.deadline = setTimeout(
      () => this.fail(connection, 'avatar_connection_timeout'),
      demand.connectSeconds * 1000
    );
    try {
      const session = await this.deps.api.start(
        connection.owner,
        demand,
        connection.controller.signal
      );
      connection.lease = session.lease_id;
      if (connection.closing || !sameAvatar(demand, this.demand)) return;
      const fresh = () => this.connection === connection && !connection.closing;
      connection.wire = this.deps.wire({
        onVideo: stream => {
          if (fresh()) this.media.video(stream);
        },
        onAudio: stream => {
          if (fresh()) this.media.audio(stream);
        },
        onControl: control => {
          // Only whitelisted controls, never raw provider messages or tokens.
          // ACK/SILENT are neither readiness nor end-of-phrase.
          if (fresh())
            logger.debug('avatar_provider_control', { component: 'AvatarEngine', control });
        },
        onError: () => {
          if (fresh()) this.fail(connection, 'avatar_transport_failed');
        },
        onClosed: () => {
          if (fresh()) this.fail(connection, 'avatar_transport_closed');
        },
      });
      await connection.wire.connect(session, connection.controller.signal);
      if (!fresh()) return;
      this.heartbeat = setInterval(() => void this.checkHeartbeat(connection), 15_000);
      // Provider lifetime begins at mint, so renew conservatively before its cap.
      this.renewal = setTimeout(
        () => this.renew(connection),
        Math.max(1000, session.max_session_seconds * 1000 - (performance.now() - mintedAt) - 15_000)
      );
      this.mediaChanged();
    } catch (error) {
      if (error instanceof AvatarStartError) connection.refused = error.beforeMint;
      if (!connection.closing)
        this.fail(
          connection,
          error instanceof AvatarStartError ? error.code : 'avatar_connect_failed'
        );
    }
  }
  private mediaChanged(): void {
    if (this.status === 'ready' && !this.media.ready) this.publish('connecting');
    if (this.connection?.closing || !this.connection?.wire) return;
    if (!this.media.ready && !this.media.connected) return;
    if (this.deadline) clearTimeout(this.deadline);
    this.deadline = null;
    this.publish(this.media.ready ? 'ready' : 'connecting');
  }
  private heartbeatPending = false;
  private async checkHeartbeat(connection: Connection): Promise<void> {
    if (this.heartbeatPending || connection.closing || !connection.lease) return;
    this.heartbeatPending = true;
    try {
      await this.deps.api.heartbeat(
        { owner_id: connection.owner, lease_id: connection.lease },
        connection.demand,
        connection.controller.signal
      );
    } catch {
      if (!connection.closing) this.fail(connection, 'avatar_heartbeat_failed');
    } finally {
      this.heartbeatPending = false;
    }
  }
  private fail(connection: Connection, code: AvatarFailureCode = 'avatar_output_failed'): void {
    if (this.connection !== connection || connection.closing) return;
    logger.warn('avatar_unavailable', { component: 'AvatarEngine', code });
    this.failureCode = code;
    this.failed = this.demand;
    this.stopWire(connection);
    this.publish(this.demand ? 'unavailable' : 'off');
    void this.reconcile();
  }
  private renew(connection: Connection): void {
    if (this.connection !== connection || connection.closing) return;
    this.stopWire(connection);
    this.publish('reconnecting');
    void this.reconcile();
  }
  private stopWire(connection: Connection): void {
    if (connection.closing) return;
    connection.closing = true;
    this.clearTimers();
    this.interrupt();
    connection.controller.abort();
    connection.wire?.close();
    this.media.reset();
  }
  private async release(connection: Connection): Promise<void> {
    if (connection.refused) {
      if (this.connection === connection) this.connection = null;
      return;
    }
    const identity = {
      owner_id: connection.owner,
      ...(connection.lease ? { lease_id: connection.lease } : {}),
    };
    let released = await this.deps.api.release(identity);
    if (!released && !this.disposed) {
      await new Promise(resolve => setTimeout(resolve, 500));
      released = await this.deps.api.release(identity);
    }
    if (!released) this.blocked = connection;
    if (this.connection === connection) this.connection = null;
  }
  async retry(): Promise<void> {
    if (this.disposed || this.busy || this.connection) return;
    if (this.blocked) {
      const released = await this.deps.api.release({
        owner_id: this.blocked.owner,
        ...(this.blocked.lease ? { lease_id: this.blocked.lease } : {}),
      });
      if (!released) return;
      this.blocked = null;
    }
    this.failed = null;
    await this.reconcile();
  }
  async settled(): Promise<void> {
    await this.reconcile();
    // Wait only for this engine's bounded API/close operation, never for speech.
    const deadline = performance.now() + 12_000;
    while (this.busy && performance.now() < deadline)
      await new Promise(resolve => setTimeout(resolve, 20));
  }
  send(packet: Uint8Array): boolean {
    return this.ready && !!this.connection?.wire?.sendPcm(packet);
  }
  outputFailed(): void {
    if (this.connection) this.fail(this.connection);
  }
  streaming(sampleRate: number, onAudible: () => void): SimliPlayout {
    if (!this.ready) throw new Error('avatar_output_unavailable');
    this.phrase?.cancel();
    this.phrase = new SimliPlayout(this, sampleRate, onAudible);
    return this.phrase;
  }
  /**
   * Open the phrase of one production (a spoken answer, whatever its number
   * of clips). A failure that may already have been heard closes the avatar
   * output for this connection and is never replayed locally; a cancellation
   * (a new production, a stop) keeps the connection.
   */
  openPhrase(sampleRate: number, onAudible: () => void): AvatarPhrase {
    const playout = this.streaming(sampleRate, onAudible);
    const failed = (signal: AbortSignal | null): never => {
      if (!signal?.aborted && this.phrase === playout && this.connection) this.fail(this.connection);
      if (this.phrase === playout) this.phrase = null;
      throw new Error(signal?.aborted ? 'avatar_phrase_cancelled' : 'avatar_playback_failed');
    };
    return {
      feed: async (buffer, signal) => {
        logger.debug('avatar_audio_decoded', {
          component: 'AvatarEngine',
          rate: buffer.sampleRate,
          frames: buffer.length,
          channels: buffer.numberOfChannels,
        });
        try {
          await pushDecoded(playout, buffer, signal);
        } catch {
          failed(signal);
        }
      },
      finish: async () => {
        try {
          await playout.finish();
        } catch {
          // A phrase interrupted meanwhile (a new production, a stop, a mode
          // switch) has nothing left to drain: that is not a failure, and it
          // never closes the connection (measured 2026-10-04: an interrupted
          // drain was logged as `avatar_playback_failed`).
          if (playout.cancelled) return;
          failed(null);
        } finally {
          if (this.phrase === playout) this.phrase = null;
        }
      },
    };
  }
  interrupt(): void {
    this.phrase?.cancel();
    this.phrase = null;
    this.media.mute();
    this.connection?.wire?.skip();
  }
  private clearTimers(): void {
    if (this.deadline) clearTimeout(this.deadline);
    if (this.heartbeat) clearInterval(this.heartbeat);
    if (this.renewal) clearTimeout(this.renewal);
    this.deadline = this.heartbeat = this.renewal = null;
  }
  dispose(): void {
    this.disposed = true;
    this.permission = false;
    this.preparing = false;
    this.demand = null;
    if (this.connection) this.stopWire(this.connection);
    this.publish('off');
    this.media.reset(true);
    void this.reconcile();
  }
}
