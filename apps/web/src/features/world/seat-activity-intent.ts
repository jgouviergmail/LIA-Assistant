/** A panel is a consequence of an acknowledged local seat request, never prediction. */
import type { WorldView } from './protocol';
interface Request {
  slot: string;
  seq: number;
  epoch: string;
  stream: number;
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
  accept(view: WorldView, stream: number, now: number): string | null {
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
    this.cancel();
    return view.pose_result === 'accepted' && view.you?.pose === pending.slot ? pending.slot : null;
  }
}
