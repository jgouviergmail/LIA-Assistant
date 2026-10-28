/** A local offer follows a confirmed generic seat, never snapshot hydration. */
import { seatContext } from './seat-context';
import type { ConfirmedSeat } from './seat-activity-intent';

export interface SeatScope {
  stream: number;
  epoch: string;
}
export interface DashboardOffer {
  slot: string;
  tableKey: string;
}
/** The consent dialog shows exactly while its offer names the seat still held; nothing else pauses. */
export function dashboardOfferOpen(
  offer: DashboardOffer | null,
  pose: string | null,
  seatKey: string | null,
  active: boolean
): boolean {
  return active && seatKey !== null && offer !== null && offer.slot === pose;
}
export class SeatDashboardIntent {
  private last: ConfirmedSeat | null = null;
  private offer: DashboardOffer | null = null;
  private listeners = new Set<() => void>();
  getSnapshot = (): DashboardOffer | null => this.offer;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  confirm(receipt: ConfirmedSeat, scope: SeatScope): boolean {
    if (receipt.stream !== scope.stream || receipt.epoch !== scope.epoch) return false;
    if (
      this.last?.stream === scope.stream &&
      this.last.epoch === scope.epoch &&
      receipt.seq <= this.last.seq
    )
      return false;
    this.last = { ...receipt };
    return this.request(receipt.slot);
  }
  /** Explicit contextual choice; the host supplies its current authoritative seat. */
  request(slot: string): boolean {
    const context = seatContext(slot);
    this.publish(
      context?.tableKey && context.dashboardEligible ? { slot, tableKey: context.tableKey } : null
    );
    return this.offer !== null;
  }
  cancel(): void {
    this.publish(null);
  }
  private publish(offer: DashboardOffer | null): void {
    if (this.offer === offer) return;
    this.offer = offer;
    for (const listener of this.listeners) listener();
  }
}
