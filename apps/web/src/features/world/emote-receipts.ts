/** A sent gesture is answered by its own server receipt; replays and reconnects never answer it. */
import type { EmoteOutcome } from './emote-catalogue';
import type { WorldView } from './protocol';

export const EMOTE_RECEIPT_TIMEOUT_MS = 5000;
interface Sent {
  seq: number;
  epoch: string;
  stream: number;
  now: number;
}
export class EmoteReceipts {
  private pending: Sent | null = null;
  arm(sent: Sent): void {
    this.pending = { ...sent };
  }
  cancel(): void {
    this.pending = null;
  }
  /** The outcome of the armed gesture once its receipt arrives; null while it is unknown. */
  accept(view: WorldView, stream: number, now: number): EmoteOutcome | null {
    const pending = this.pending;
    if (!pending) return null;
    if (
      pending.stream !== stream ||
      pending.epoch !== view.epoch ||
      now - pending.now >= EMOTE_RECEIPT_TIMEOUT_MS
    ) {
      this.cancel();
      return null;
    }
    if (view.ack < pending.seq) return null;
    const receipt = view.receipts.find(item => item.kind === 'emote' && item.seq === pending.seq);
    if (receipt?.kind !== 'emote') return null;
    this.cancel();
    return receipt.result;
  }
}
