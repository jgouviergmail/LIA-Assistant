import type { Ambience, SoundId, EffectSoundId } from './catalogue';
export interface SoundVoice {
  fade(level: number, seconds: number): void;
  stop(afterSeconds?: number): void;
}
export interface DecodedSound {
  bytes: number;
  duration: number;
  start(loop: boolean, offset: number): SoundVoice;
}
export interface SoundBackend {
  activate(): Promise<boolean>;
  setVolume(level: number): void;
  load(id: SoundId, signal: AbortSignal): Promise<DecodedSound>;
  suspend(): void;
  destroy(): void;
}
export const WORLD_AUDIO_CACHE_BYTES = 8 * 1024 * 1024;
const FADE = 0.9;
/** Owner-local sound state. Two ambience voices, one cue, a bounded cache, no frame-loop work. */
export class Soundscape {
  private enabled = false;
  private paused = false;
  private ready = false;
  private disposed = false;
  private scene: Ambience | null = null;
  private playing: Ambience | null = null;
  private current: SoundVoice | null = null;
  private retiring: SoundVoice | null = null;
  private cue: SoundVoice | null = null;
  /** What the single cue voice plays or loads: a message outranks every decor cue. */
  private cueKind: SoundId | null = null;
  private cueUntil = -Infinity;
  private pendingKind: SoundId | null = null;
  private request = 0;
  private pending: AbortController | null = null;
  private noticePending: AbortController | null = null;
  private cache = new Map<SoundId, DecodedSound>();
  private phoneTimer: ReturnType<typeof setTimeout> | null = null;
  private lastCue = -Infinity;
  private lastNotice = -Infinity;
  constructor(
    private backend: SoundBackend,
    private clock = { random: Math.random, now: () => performance.now() }
  ) {}
  setVolume(level: number): void {
    if (!this.disposed && Number.isFinite(level))
      this.backend.setVolume(Math.max(0, Math.min(1, level)));
  }
  get decodedBytes(): number {
    return [...this.cache.values()].reduce((sum, clip) => sum + clip.bytes, 0);
  }
  async enable(): Promise<boolean> {
    if (this.disposed) return false;
    this.enabled = true;
    try {
      this.ready = await this.backend.activate();
    } catch {
      this.ready = false;
    }
    if (!this.enabled || this.disposed) {
      this.backend.suspend();
      return false;
    }
    if (!this.ready) {
      this.enabled = false;
      return false;
    }
    if (this.paused) this.backend.suspend();
    await this.reconcile();
    return this.enabled;
  }
  disable(): void {
    this.enabled = false;
    this.ready = false;
    this.cancel();
    this.stopBeds(0);
    this.stopCue();
    this.cache.clear();
    this.backend.suspend();
  }
  pause(value: boolean): void {
    if (this.disposed || this.paused === value) return;
    this.paused = value;
    if (value) {
      this.cancel();
      this.stopBeds(0);
      this.stopCue();
      this.ready = false;
      this.backend.suspend();
    } else if (this.enabled) void this.enable();
  }
  async select(scene: Ambience | null): Promise<void> {
    if (this.disposed || this.scene === scene) return;
    this.scene = scene;
    this.cancel();
    await this.reconcile();
  }
  private allowed(): boolean {
    return this.enabled && this.ready && !this.paused && !this.disposed;
  }
  private cancel(): void {
    this.request++;
    this.pending?.abort();
    this.pending = null;
    if (this.phoneTimer !== null) clearTimeout(this.phoneTimer);
    this.phoneTimer = null;
  }
  private stopBeds(seconds: number): void {
    this.retiring?.stop();
    this.retiring = this.current;
    if (this.current) {
      this.current.fade(0, seconds);
      this.current.stop(seconds);
    }
    this.current = null;
    this.playing = null;
  }
  private stopCue(): void {
    this.noticePending?.abort();
    this.noticePending = null;
    this.pendingKind = null;
    this.cue?.stop();
    this.cue = null;
    this.cueKind = null;
    this.cueUntil = -Infinity;
  }
  private messageHeld(): boolean {
    return (
      this.pendingKind === 'message' ||
      (this.cueKind === 'message' && this.clock.now() < this.cueUntil)
    );
  }
  private async reconcile(): Promise<void> {
    if (!this.allowed()) return;
    if (this.scene === null) {
      this.stopBeds(FADE);
      return;
    }
    if (this.playing === this.scene || this.pending) return;
    if (this.scene === 'phone') {
      this.stopBeds(FADE);
      this.queuePhone(true);
      return;
    }
    await this.play(this.scene, this.request);
  }
  private queuePhone(first: boolean): void {
    if (this.phoneTimer !== null || !this.allowed() || this.scene !== 'phone') return;
    const request = this.request;
    this.phoneTimer = setTimeout(
      () => {
        this.phoneTimer = null;
        void this.play('phone', request);
      },
      (first ? 20000 : 45000) + this.clock.random() * (first ? 20000 : 30000)
    );
  }
  private async read(id: SoundId, signal: AbortSignal): Promise<DecodedSound> {
    const cached = this.cache.get(id);
    if (cached) {
      this.cache.delete(id);
      this.cache.set(id, cached);
      return cached;
    }
    const clip = await this.backend.load(id, signal);
    if (signal.aborted || this.disposed) throw new Error('World sound cancelled');
    if (
      !Number.isFinite(clip.bytes + clip.duration) ||
      clip.bytes <= 0 ||
      clip.bytes > WORLD_AUDIO_CACHE_BYTES ||
      clip.duration <= 0 ||
      clip.duration > 33
    )
      throw new Error('World sound outside bounds');
    while (
      this.cache.size &&
      (this.decodedBytes + clip.bytes > WORLD_AUDIO_CACHE_BYTES || this.cache.size >= 3)
    ) {
      const oldest = this.cache.keys().next().value;
      if (oldest !== undefined) this.cache.delete(oldest);
    }
    this.cache.set(id, clip);
    return clip;
  }
  private async play(id: Ambience, request: number): Promise<void> {
    if (!this.allowed() || request !== this.request) return;
    const controller = new AbortController();
    this.pending = controller;
    try {
      const clip = await this.read(id, controller.signal);
      if (!this.allowed() || controller.signal.aborted || request !== this.request) return;
      this.stopBeds(FADE);
      this.current = clip.start(
        id !== 'phone',
        id === 'phone' ? 0 : this.clock.random() * Math.max(0, clip.duration - 1)
      );
      this.current.fade(id === 'phone' ? 0.2 : 0.3, FADE);
      this.playing = id;
    } catch {
      if (!controller.signal.aborted && request === this.request) this.stopBeds(0.3);
    } finally {
      if (this.pending === controller) this.pending = null;
      if (id === 'phone' && request === this.request) this.queuePhone(false);
    }
  }
  async notify(): Promise<void> {
    const at = this.clock.now();
    if (!this.allowed() || at - this.lastNotice < 800) return;
    this.lastNotice = at;
    await this.playCue('message', () => true);
  }
  async effect(id: EffectSoundId, current: () => boolean): Promise<void> {
    const at = this.clock.now();
    if (
      !this.allowed() ||
      !current() ||
      this.messageHeld() ||
      at - this.lastNotice < 1200 ||
      at - this.lastCue < 800
    )
      return;
    this.lastCue = at;
    await this.playCue(id, current);
  }
  private async playCue(id: SoundId, current: () => boolean): Promise<void> {
    const at = this.clock.now();
    const controller = new AbortController();
    this.noticePending?.abort();
    this.noticePending = controller;
    this.pendingKind = id;
    try {
      const clip = await this.read(id, controller.signal);
      if (
        !this.allowed() ||
        !current() ||
        controller.signal.aborted ||
        this.clock.now() - at > 3000
      )
        return;
      this.cue?.stop();
      this.cue = clip.start(false, 0);
      this.cueKind = id;
      this.cueUntil = this.clock.now() + clip.duration * 1000;
      this.cue.fade(id === 'message' ? 0.7 : 0.6, 0.02);
    } catch {
      /* A missing cue must never interrupt reading a message. */
    } finally {
      if (this.noticePending === controller) {
        this.noticePending = null;
        this.pendingKind = null;
      }
    }
  }
  destroy(): void {
    if (this.disposed) return;
    this.disable();
    this.disposed = true;
    this.cache.clear();
    this.backend.destroy();
  }
}
