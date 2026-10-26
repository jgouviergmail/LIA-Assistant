import type { WorldMailbox } from '../message-protocol';
/** IDs only. Silent first read and reconnection; no public broadcast or outgoing echo. */
export class RecipientChime {
  private active = false;
  private baseline = false;
  private seen = new Set<string>();
  setActive(active: boolean): void {
    if (this.active === active) return;
    this.active = active;
    if (!active) this.baseline = false;
  }
  receive(mailbox: WorldMailbox): boolean {
    if (!this.active || !Number.isFinite(mailbox.server_time)) return false;
    let fresh = false;
    for (const message of mailbox.messages) {
      const known = this.seen.has(message.id);
      this.seen.add(message.id);
      if (this.seen.size > 224) {
        const first = this.seen.values().next().value;
        if (first !== undefined) this.seen.delete(first);
      }
      if (!this.baseline || known || message.outgoing) continue;
      const age = mailbox.server_time - message.created_at;
      if (Number.isFinite(age) && age >= -5 && age <= 15) fresh = true;
    }
    this.baseline = true;
    return fresh;
  }
}
