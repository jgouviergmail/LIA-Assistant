/** A panel is a consequence of an acknowledged local seat request, never prediction. */
import type { WorldView } from './protocol';
export interface ConfirmedSeat {
  slot: string;
  seq: number;
  epoch: string;
  stream: number;
}
interface Request extends ConfirmedSeat {
  now: number;
}
export class SeatActivityIntent {
  private pending: Request | null = null;
  arm(request: Request): void {
    this.pending = { ...request };
  }
  cancel(): void {
    this.pending = null;
  }
  accept(view: WorldView, stream: number, now: number): ConfirmedSeat | null {
    const pending = this.pending;
    if (!pending) return null;
    if (
      pending.stream !== stream ||
      pending.epoch !== view.epoch ||
      !view.controlling ||
      view.status !== 'active' ||
      now - pending.now >= 5000
    ) {
      this.cancel();
      return null;
    }
    if (view.ack < pending.seq) return null;
    const receipt = view.receipts.find(item => item.seq === pending.seq && item.kind === 'pose');
    if (!receipt || receipt.kind !== 'pose') return null;
    this.cancel();
    return receipt.result === 'accepted' && view.you?.pose === pending.slot
      ? { slot: pending.slot, seq: pending.seq, epoch: pending.epoch, stream: pending.stream }
      : null;
  }
}
