import { AVATAR_PCM_MAX_BACKLOG_BYTES, AVATAR_PCM_PACKET_BYTES } from './types';

export class PcmPacketizer {
  private pending = new Uint8Array(AVATAR_PCM_PACKET_BYTES);
  private length = 0;
  push(bytes: Uint8Array): Uint8Array[] {
    if (bytes.length % 2 || bytes.length > AVATAR_PCM_MAX_BACKLOG_BYTES) {
      throw new Error('voice_invalid_pcm_packet');
    }
    const packets: Uint8Array[] = [];
    for (let offset = 0; offset < bytes.length; ) {
      const size = Math.min(this.pending.length - this.length, bytes.length - offset);
      this.pending.set(bytes.subarray(offset, offset + size), this.length);
      this.length += size;
      offset += size;
      if (this.length === this.pending.length) {
        packets.push(this.pending.slice());
        this.length = 0;
      }
    }
    return packets;
  }
  finish(): Uint8Array | null {
    if (!this.length) return null;
    const tail = this.pending.slice(0, this.length);
    this.length = 0;
    return tail;
  }
  clear(): void {
    this.length = 0;
  }
}
