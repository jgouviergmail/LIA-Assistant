import type { LivePlayer } from '../live/session-controller';
import type { AvatarEngine } from '../avatars/engine';
import type { SimliPlayout } from '../avatars/playout';
import { RemotePcmCapture } from './remote-capture';
import { LIVE_PCM_PRODUCTION_HOLD_MS, LIVE_PCM_TAIL_HOLD_MS } from './types';
import { logger } from '@/lib/logger';

interface Route {
  target: AvatarEngine | null;
  phrase: SimliPlayout | null;
  failed: boolean;
}

function validPcm(pcm: ArrayBuffer, rate: number): boolean {
  return (
    Number.isInteger(rate) &&
    rate >= 8000 &&
    rate <= 96000 &&
    pcm.byteLength > 0 &&
    pcm.byteLength % 2 === 0 &&
    pcm.byteLength <= rate * 10
  );
}

/** PCM owns one destination until production and real output have drained. */
export class RoutedLivePlayer implements LivePlayer {
  private route: Route | null = null;
  private speaking = false;
  private listener: (speaking: boolean) => void = () => {};
  private draining = false;
  private productionDone = false;
  private disposed = false;
  private epoch = 0;
  private pending: { pcm: ArrayBuffer; rate: number }[] = [];
  private pendingBytes = 0;
  private pendingTarget: AvatarEngine | null = null;
  private pendingDone = false;
  private readonly capture: RemotePcmCapture;
  private native = false;
  private nativeActive = false;
  private nativeIdle = true;
  private nativeBlocked = false;
  private nativeFallback = false;
  private preRoll: ArrayBuffer | null = null;
  private activityTimer: ReturnType<typeof setInterval> | null = null;
  private directAudio: HTMLAudioElement | null = null;
  private remoteStream: MediaStream | null = null;
  private releaseCapture: (() => void) | null = null;
  private stopPermission: (() => void) | null = null;
  private nextNativeResponse = false;
  private attachment = 0;
  private lastChunkAt = 0;
  private boundaryTimer: ReturnType<typeof setTimeout> | null = null;
  constructor(
    readonly local: LivePlayer,
    readonly avatar: () => AvatarEngine | null
  ) {
    this.capture = new RemotePcmCapture(
      (pcm, rate) => this.receiveNative(pcm, rate),
      () => {
        this.flush();
        this.nativeFallback = true;
        this.avatar()?.outputFailed();
      }
    );
    local.onAudibleChange?.(value => {
      if (this.native && !this.route?.target) this.notify(value);
    });
    local.onSpeakingChange(value => {
      if (this.route?.target) return;
      if (!this.native) this.notify(value);
      if (!value && this.productionDone) this.drainNext(this.epoch);
    });
  }
  get isSpeaking(): boolean {
    return this.native || this.route?.target ? this.speaking : this.local.isSpeaking;
  }
  async warmup(): Promise<void> {
    const unlock = this.avatar()?.media.unlock();
    const capture = this.capture.warmup();
    await this.local.warmup();
    await unlock;
    await capture;
  }
  attachRemoteStream(stream: MediaStream): () => void {
    if (this.disposed) return () => {};
    this.releaseRemoteStream();
    const attachment = ++this.attachment;
    this.native = true;
    this.nativeBlocked = false;
    this.nativeFallback = false;
    this.remoteStream = stream;
    const engine = this.avatar();
    if (engine?.permitted) this.beginNativeCapture();
    else {
      // Preserve native playback for an account that has never opted in.
      const audio = document.createElement('audio');
      audio.autoplay = true;
      audio.srcObject = stream;
      audio.style.display = 'none';
      document.body.appendChild(audio);
      this.directAudio = audio;
      void audio.play().catch(() => {
        if (attachment === this.attachment && !this.disposed) this.notify(false);
      });
    }
    this.stopPermission =
      engine?.subscribe(() => {
        if (!engine.permitted) this.nextNativeResponse = false;
      }) ?? null;
    this.activityTimer ??= setInterval(() => {
      if (this.route?.target)
        this.notify(!this.route.target.media.quiet && this.route.target.ready);
    }, 20);
    return () => {
      if (attachment !== this.attachment) return;
      this.attachment++;
      this.releaseRemoteStream();
    };
  }
  private releaseRemoteStream(): void {
    this.stopPermission?.();
    this.stopPermission = null;
    this.releaseCapture?.();
    this.releaseCapture = null;
    this.directAudio?.pause();
    if (this.directAudio) this.directAudio.srcObject = null;
    this.directAudio?.remove();
    this.directAudio = null;
    this.remoteStream = null;
    if (this.activityTimer) clearInterval(this.activityTimer);
    this.activityTimer = null;
    this.flush();
    this.native = false;
  }
  /** Hot opt-in waits for a new human request, never takes over a spoken prefix. */
  prepareNativeResponse(): void {
    if (!this.directAudio || !this.avatar()?.permitted) return;
    this.nextNativeResponse = true;
    if (this.nativeIdle && !this.isSpeaking) this.beginNativeCapture();
  }
  private beginNativeCapture(): void {
    const stream = this.remoteStream;
    if (!stream) return;
    this.directAudio?.pause();
    if (this.directAudio) this.directAudio.srcObject = null;
    this.directAudio?.remove();
    this.directAudio = null;
    this.releaseCapture?.();
    this.releaseCapture = this.capture.attach(stream);
    this.nativeActive = false;
    this.nextNativeResponse = false;
  }
  /** False is only a provider hint, never an EOF or a reason to drop the tail. */
  nativeSpeaking(speaking: boolean): void {
    if (this.disposed) return;
    if (this.nativeFallback) {
      this.notify(speaking);
      return;
    }
    if (this.directAudio) {
      this.nativeIdle = !speaking;
      this.notify(speaking);
      if (!speaking && this.nextNativeResponse) this.beginNativeCapture();
      return;
    }
    if (!this.native) return;
    if (!speaking) {
      this.nativeIdle = true;
      return;
    }
    if (this.nativeIdle && this.nativeActive && !this.isSpeaking) {
      this.finishProduction();
      this.nativeActive = false;
    }
    this.nativeIdle = false;
  }
  private receiveNative(pcm: ArrayBuffer, rate: number): void {
    if (this.disposed) return;
    const samples = new DataView(pcm);
    let sound = false;
    for (let offset = 0; offset < pcm.byteLength; offset += 2) {
      if (samples.getInt16(offset, true) !== 0) {
        sound = true;
        break;
      }
    }
    if (this.nativeBlocked) {
      if (!sound) this.nativeBlocked = false;
      return;
    }
    if (!this.nativeActive && !sound) {
      this.preRoll = pcm.slice(0);
      return;
    }
    if (!this.nativeActive) {
      this.nativeActive = true;
      if (this.preRoll) this.enqueue(this.preRoll, rate);
      this.preRoll = null;
    }
    // Every block after the first sound survives: weak audio and interior pauses.
    this.enqueue(pcm, rate);
  }
  enqueue(pcm: ArrayBuffer, rate: number): void {
    if (this.disposed) return;
    if (!validPcm(pcm, rate)) {
      this.failed();
      return;
    }
    this.armBoundary();
    if (this.draining) {
      this.queueNext(pcm, rate);
      return;
    }
    this.productionDone = false;
    if (!this.route) this.route = this.select(rate, this.avatar());
    if (this.route.failed) return;
    if (this.route.phrase && this.route.phrase.sampleRate !== rate) {
      this.failed();
      return;
    }
    if (!this.route.target) {
      this.local.enqueue(pcm, rate);
      return;
    }
    try {
      this.route.phrase?.pushPcm(pcm);
    } catch {
      this.failed();
    }
  }
  private select(rate: number, target: AvatarEngine | null): Route {
    // The same development diagnostic as the comments' coordinator: which
    // destination this production took, and why (counts and flags only).
    logger.info('voice_output_selected', {
      component: 'RoutedLivePlayer',
      source: 'live',
      route: target?.ready ? 'avatar' : 'local',
      avatarReady: target?.ready ?? false,
      avatarState: target?.state ?? 'none',
      native: this.native,
      rate,
    });
    if (!target?.ready) return { target: null, phrase: null, failed: false };
    const epoch = this.epoch;
    return {
      target,
      failed: false,
      phrase: target.streaming(rate, () => {
        if (epoch === this.epoch && !this.disposed) this.notify(true);
      }),
    };
  }
  private queueNext(pcm: ArrayBuffer, rate: number): void {
    if (this.pendingBytes + pcm.byteLength > rate * 10) {
      this.failed();
      return;
    }
    if (!this.pending.length) {
      const candidate = this.avatar();
      this.pendingTarget = candidate?.ready ? candidate : null;
    }
    this.pending.push({ pcm: pcm.slice(0), rate });
    this.pendingBytes += pcm.byteLength;
    this.pendingDone = false;
  }
  /**
   * The production boundary every transport shares: no chunk for a while and
   * the output drained. A provider's own EOF (`finishProduction` from Gemini's
   * `generationComplete`) or speaking hint only shortens it. ElevenLabs over
   * WebSocket has neither for its audio — its `agent_response` PRECEDES the
   * chunks — so without this the route chosen for the first reply held for the
   * whole session (measured 2026-10-04: a cold start left every reply local).
   */
  private armBoundary(): void {
    this.lastChunkAt = performance.now();
    this.boundaryTimer ??= setTimeout(() => this.checkBoundary(), LIVE_PCM_TAIL_HOLD_MS);
  }
  private checkBoundary(): void {
    this.boundaryTimer = null;
    if (this.disposed || this.draining || !this.route) return;
    const idle = performance.now() - this.lastChunkAt;
    if (idle < LIVE_PCM_TAIL_HOLD_MS) {
      this.scheduleBoundary(LIVE_PCM_TAIL_HOLD_MS - idle);
      return;
    }
    // The provider paused: its last partial packet leaves now, never with a next chunk.
    if (!this.route.failed) this.route.phrase?.flushTail();
    if (idle >= LIVE_PCM_PRODUCTION_HOLD_MS) {
      if (!this.productionDone) this.finishProduction();
      return;
    }
    this.scheduleBoundary(LIVE_PCM_PRODUCTION_HOLD_MS - idle);
  }
  private scheduleBoundary(delay: number): void {
    this.boundaryTimer = setTimeout(() => this.checkBoundary(), Math.ceil(delay));
  }
  private disarmBoundary(): void {
    if (this.boundaryTimer) clearTimeout(this.boundaryTimer);
    this.boundaryTimer = null;
  }
  finishProduction(): void {
    if (this.disposed) return;
    if (this.draining) {
      if (this.pending.length) this.pendingDone = true;
      return;
    }
    this.productionDone = true;
    const route = this.route;
    if (!route?.phrase || route.failed) {
      if (!this.local.isSpeaking || (this.native && !this.speaking)) this.route = null;
      else this.draining = true;
      return;
    }
    this.draining = true;
    const epoch = this.epoch;
    void route.phrase
      .finish()
      .catch(() => {
        if (epoch === this.epoch) this.failed();
      })
      .finally(() => {
        this.drainNext(epoch);
      });
  }
  private drainNext(epoch: number): void {
    if (epoch !== this.epoch) return;
    logger.debug('voice_output_production_ended', {
      component: 'RoutedLivePlayer',
      queued: this.pending.length,
    });
    this.draining = false;
    this.route = null;
    this.notify(false);
    const pending = this.pending;
    const target = this.pendingTarget;
    const done = this.pendingDone;
    this.pending = [];
    this.pendingBytes = 0;
    this.pendingTarget = null;
    this.pendingDone = false;
    if (pending.length) this.route = this.select(pending[0].rate, target);
    for (const item of pending) this.enqueue(item.pcm, item.rate);
    if (done) this.finishProduction();
  }
  private failed(): void {
    logger.warn('voice_output_route_failed', {
      component: 'RoutedLivePlayer',
      route: this.route?.target ? 'avatar' : 'local',
    });
    if (this.route) {
      this.route.failed = true;
      this.route.phrase?.cancel();
      this.route.target?.outputFailed();
    }
    this.pending = [];
    this.pendingBytes = 0;
    this.pendingTarget = null;
    this.pendingDone = false;
    this.notify(false);
  }
  private notify(value: boolean): void {
    if (this.disposed && value) return;
    if (value === this.speaking) return;
    this.speaking = value;
    this.listener(value);
  }
  flush(): void {
    this.epoch++;
    this.disarmBoundary();
    this.route?.phrase?.cancel();
    this.route?.target?.interrupt();
    this.route = null;
    this.draining = false;
    this.productionDone = false;
    this.pending = [];
    this.pendingBytes = 0;
    this.pendingTarget = null;
    this.pendingDone = false;
    this.local.flush();
    this.notify(false);
    this.nativeActive = false;
    this.nativeIdle = true;
    this.preRoll = null;
    if (this.native && !this.directAudio) {
      this.nativeBlocked = true;
      this.capture.flush();
    }
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.disarmBoundary();
    this.attachment++;
    this.releaseRemoteStream();
    this.local.dispose();
    this.capture.dispose();
  }
  onSpeakingChange(listener: (speaking: boolean) => void): void {
    this.listener = listener;
  }
  diagnostics() {
    return this.local.diagnostics?.() ?? null;
  }
}
