import {
  AVATAR_PCM_MAX_BACKLOG_BYTES,
  AVATAR_PCM_PACKET_BYTES,
  AVATAR_PCM_SEND_STALL_MS,
} from './types';

/**
 * PCM leaves as soon as the transport accepts it; the provider buffers ahead.
 *
 * Its reference client forwards every TTS chunk unpaced and empties the
 * provider's buffer with SKIP on an interruption. Pacing packets to the sample
 * clock instead left the provider ~85 ms of lead (measured: first remote sound
 * 290 ms after the first of two 187.5 ms packets), so a decode, a render or a
 * throttled tab starved it into silence frames — a mouth closing at the packet
 * cadence. Backpressure is the socket's own (`send` answers false), bounded in
 * memory (`AVATAR_PCM_MAX_BACKLOG_BYTES`) and in time (`AVATAR_PCM_SEND_STALL_MS`).
 */
export class PcmSendQueue {
  private queue: Uint8Array[] = [];
  private bytes = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private blockedAt: number | null = null;
  private epoch = 0;
  private disposed = false;
  constructor(
    readonly send: (packet: Uint8Array) => boolean,
    readonly failed: (error: Error) => void
  ) {}
  enqueue(packet: Uint8Array): void {
    if (this.disposed) throw new Error('voice_sender_disposed');
    if (packet.length % 2 || !packet.length || packet.length > AVATAR_PCM_PACKET_BYTES) {
      throw new Error('voice_invalid_pcm_packet');
    }
    if (this.bytes + packet.length > AVATAR_PCM_MAX_BACKLOG_BYTES) {
      throw new Error('voice_pcm_backlog_full');
    }
    this.queue.push(packet.slice());
    this.bytes += packet.length;
    if (this.timer === null) this.pump();
  }

  private pump(): void {
    const epoch = this.epoch;
    while (this.queue.length) {
      const packet = this.queue[0];
      let accepted: boolean;
      try {
        accepted = this.send(packet);
      } catch {
        this.clear();
        this.failed(new Error('voice_pcm_send_failed'));
        return;
      }
      // A synchronous teardown inside `send` owns the queue from here.
      if (epoch !== this.epoch) return;
      if (!accepted) {
        this.blocked(performance.now());
        return;
      }
      this.queue.shift();
      this.bytes -= packet.length;
      this.blockedAt = null;
    }
  }

  private blocked(now: number): void {
    this.blockedAt ??= now;
    if (now - this.blockedAt >= AVATAR_PCM_SEND_STALL_MS) {
      this.clear();
      this.failed(new Error('voice_pcm_send_stalled'));
      return;
    }
    this.schedule(20);
  }

  private schedule(delay: number): void {
    const epoch = this.epoch;
    this.timer = setTimeout(() => {
      if (epoch !== this.epoch) return;
      this.timer = null;
      this.pump();
    }, delay);
  }

  clear(): void {
    this.epoch++;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.queue = [];
    this.bytes = 0;
    this.blockedAt = null;
  }
  dispose(): void {
    this.clear();
    this.disposed = true;
  }
  get pendingBytes(): number {
    return this.bytes;
  }
}
