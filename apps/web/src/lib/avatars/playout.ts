import { Pcm16Resampler, decodePcm16 } from '../voice-output/pcm-resampler';
import { PcmPacketizer } from '../voice-output/pcm-packetizer';
import { PcmSendQueue } from '../voice-output/pcm-send-queue';
import { AVATAR_PCM_LEAD_MAX_SECONDS, AVATAR_PCM_SAMPLE_RATE } from '../voice-output/types';
import type { AvatarMedia } from './engine';
import { logger } from '@/lib/logger';

export interface PlayoutTarget {
  readonly media: AvatarMedia;
  readonly ready: boolean;
  send(packet: Uint8Array): boolean;
}
function pause(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, 20);
    signal.addEventListener('abort', abort, { once: true });
  });
}

/**
 * A phrase owns its converter, its estimated playback clock and its drain. It spans one
 * PRODUCTION — every clip of a spoken answer, every chunk of a Live reply —
 * so the face never idles and restarts between two sentences of one answer
 * (measured 2026-10-04: ~0.3 s of drain plus ~0.3 s of remote onset per clip).
 * SILENT never ends it: the provider plays what it holds at its own pace, and
 * the drain is read from the clock of what was submitted and from the observed
 * remote output, never from a provider control.
 */
export class SimliPlayout {
  private readonly converter: Pcm16Resampler;
  private readonly packetizer = new PcmPacketizer();
  private readonly sender: PcmSendQueue;
  private readonly controller = new AbortController();
  private firstSent: number | null = null;
  /** Estimated local-clock end of the submitted audio, before `delay`. */
  private scheduledEnd = 0;
  private delay = 1;
  private expectsSound = false;
  private heard = false;
  private sentSamples = 0;
  private sentPackets = 0;
  private error: Error | null = null;
  private finished = false;
  constructor(
    readonly target: PlayoutTarget,
    readonly sampleRate: number,
    onAudible: () => void
  ) {
    this.converter = new Pcm16Resampler(sampleRate);
    this.sender = new PcmSendQueue(
      packet => {
        if (!target.send(packet)) return false;
        this.sentSamples += packet.length / 2;
        this.sentPackets++;
        this.expectsSound ||= packet.some(byte => byte !== 0);
        const now = target.media.clock;
        this.firstSent ??= now;
        // The provider queues what it receives: a packet plays after the
        // previous one, never before it arrived.
        this.scheduledEnd =
          Math.max(this.scheduledEnd, now) + packet.length / (AVATAR_PCM_SAMPLE_RATE * 2);
        return true;
      },
      error => {
        this.error = error;
        this.cancel();
      }
    );
    target.media.begin(() => {
      if (this.controller.signal.aborted) return;
      this.heard = true;
      if (this.firstSent !== null) this.delay = Math.max(0, target.media.clock - this.firstSent);
      onAudible();
    });
  }
  get pendingBytes(): number {
    return this.sender.pendingBytes;
  }
  /** Estimated seconds of submitted audio remaining, before `delay`. */
  get lead(): number {
    return Math.max(0, this.scheduledEnd - this.target.media.clock);
  }
  /** Interrupted by its owner: nothing is left to drain, and nothing failed. */
  get cancelled(): boolean {
    return this.controller.signal.aborted;
  }
  /** Cancelled, failed or finished: nothing more may join. */
  get closed(): boolean {
    return this.error !== null || this.finished || this.controller.signal.aborted;
  }
  push(channels: readonly Float32Array[]): void {
    this.assertOpen();
    for (const packet of this.packetizer.push(this.converter.push(channels)))
      this.sender.enqueue(packet);
  }
  pushPcm(data: ArrayBuffer): void {
    if (data.byteLength > this.sampleRate * 10) throw new Error('avatar_pcm_backlog_full');
    this.push([decodePcm16(data)]);
  }
  /**
   * A clip or a pause ended here: its partial last packet leaves now rather
   * than with the next clip, which may be a second away. A no-op once closed.
   */
  flushTail(): void {
    if (this.closed) return;
    const tail = this.packetizer.finish();
    if (tail) this.sender.enqueue(tail);
  }
  private assertOpen(): void {
    if (this.error) throw this.error;
    if (this.controller.signal.aborted || this.finished) throw new Error('avatar_phrase_closed');
    if (!this.target.ready) throw new Error('avatar_output_unavailable');
  }
  async finish(): Promise<void> {
    this.assertOpen();
    this.finished = true;
    for (const packet of this.packetizer.push(this.converter.finish())) this.sender.enqueue(packet);
    const tail = this.packetizer.finish();
    if (tail) this.sender.enqueue(tail);
    const started = performance.now();
    try {
      while (this.sender.pendingBytes) {
        if (performance.now() - started > 10_000 + this.sender.pendingBytes / 32)
          throw new Error('avatar_drain_timeout');
        await pause(this.controller.signal);
      }
      await this.drainOutput(started);
      if (this.error) throw this.error;
    } finally {
      logger.debug('avatar_audio_submitted', {
        component: 'SimliPlayout',
        rate: AVATAR_PCM_SAMPLE_RATE,
        samples: this.sentSamples,
        packets: this.sentPackets,
        remoteSoundObserved: this.heard,
      });
      this.sender.dispose();
      this.target.media.mute();
    }
  }
  private needsDrain(): boolean {
    return (
      (this.expectsSound && !this.heard) ||
      this.target.media.clock < this.scheduledEnd + this.delay + 0.08 ||
      !this.target.media.quiet
    );
  }
  private async drainOutput(started: number): Promise<void> {
    const remaining = Math.max(0, this.scheduledEnd + this.delay + 0.08 - this.target.media.clock);
    const deadline = performance.now() + remaining * 1000 + 10_000;
    let clock = this.target.media.clock;
    let advancedAt = performance.now();
    // This clock estimates the tail. Observed sound and readiness are independent
    // guards: a running local clock alone never proves remote playback.
    while (this.needsDrain()) {
      const now = performance.now();
      if (!this.target.ready) throw new Error('avatar_output_unavailable');
      if (this.target.media.clock > clock) {
        clock = this.target.media.clock;
        advancedAt = now;
      }
      if (this.expectsSound && !this.heard && now - started > 10_000)
        throw new Error('avatar_no_remote_sound');
      if (now - advancedAt > 10_000) throw new Error('avatar_clock_stalled');
      if (now > deadline) throw new Error('avatar_drain_timeout');
      await pause(this.controller.signal);
    }
  }
  cancel(): void {
    this.controller.abort();
    this.sender.dispose();
    this.packetizer.clear();
    this.target.media.mute();
  }
}

/**
 * One decoded clip joins the phrase. It resolves once the clip is ACCEPTED,
 * never once heard: the next clip of the same answer follows at once, and the
 * provider plays the whole stream continuously. The lead is bounded
 * (`AVATAR_PCM_LEAD_MAX_SECONDS`) so an interruption's SKIP stays cheap.
 */
export async function pushDecoded(
  phrase: SimliPlayout,
  buffer: AudioBuffer,
  signal: AbortSignal
): Promise<void> {
  const abort = () => phrase.cancel();
  signal.addEventListener('abort', abort, { once: true });
  try {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    for (let frame = 0; frame < buffer.length; frame += 2048) {
      while (phrase.pendingBytes > 64000 || phrase.lead > AVATAR_PCM_LEAD_MAX_SECONDS) {
        if (phrase.closed) throw new Error('avatar_phrase_closed');
        await pause(signal);
      }
      phrase.push(
        Array.from({ length: buffer.numberOfChannels }, (_, channel) =>
          buffer.getChannelData(channel).subarray(frame, frame + 2048)
        )
      );
    }
    // The clip ends here: its last partial packet leaves now, never held for
    // a next clip that may be a second away.
    phrase.flushTail();
  } catch {
    phrase.cancel();
    throw new Error(signal.aborted ? 'avatar_phrase_cancelled' : 'avatar_playback_failed');
  } finally {
    signal.removeEventListener('abort', abort);
  }
}
