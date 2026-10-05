import type { SimliPlayout } from '../avatars/playout';
import { AVATAR_PCM_LEAD_MAX_SECONDS, LIVE_PCM_MAX_QUEUED_SECONDS } from './types';

/** Synchronous Live callbacks feed a bounded, paced phrase without blocking the SDK. */
export class LivePcmQueue {
  private queue: { pcm: ArrayBuffer; offset: number }[] = [];
  private frames = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private ended: (() => void) | null = null;
  private disposed = false;
  private advancedAt = performance.now();
  private clock = 0;
  constructor(
    readonly phrase: SimliPlayout,
    readonly failed: (error: unknown) => void
  ) {}
  push(pcm: ArrayBuffer): void {
    if (this.disposed) return;
    if (this.frames + pcm.byteLength / 2 > this.phrase.sampleRate * LIVE_PCM_MAX_QUEUED_SECONDS)
      throw new Error('avatar_pcm_backlog_full');
    this.queue.push({ pcm: pcm.slice(0), offset: 0 });
    this.frames += pcm.byteLength / 2;
    this.pump();
  }
  finish(ended: () => void): void {
    this.ended = ended;
    this.pump();
  }
  private pump(): void {
    if (this.disposed || this.timer) return;
    try {
      if (
        this.phrase.lead > 0 &&
        this.phrase.target.media.clock === this.clock &&
        performance.now() - this.advancedAt > 10_000
      )
        throw new Error('avatar_clock_stalled');
      if (this.phrase.target.media.clock !== this.clock) {
        this.clock = this.phrase.target.media.clock;
        this.advancedAt = performance.now();
      }
      while (
        this.queue.length &&
        this.phrase.lead < AVATAR_PCM_LEAD_MAX_SECONDS &&
        this.phrase.pendingBytes < 64000
      ) {
        const item = this.queue[0];
        const end = Math.min(item.pcm.byteLength, item.offset + 4096);
        this.phrase.pushPcm(item.pcm.slice(item.offset, end));
        this.frames -= (end - item.offset) / 2;
        item.offset = end;
        if (end === item.pcm.byteLength) this.queue.shift();
      }
      if (!this.queue.length) {
        const ended = this.ended;
        this.ended = null;
        ended?.();
        return;
      }
      this.timer = setTimeout(() => {
        this.timer = null;
        this.pump();
      }, 20);
    } catch (error) {
      this.dispose();
      this.failed(error);
    }
  }
  dispose(): void {
    this.disposed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.ended = null;
    this.queue = [];
    this.frames = 0;
  }
}
