import { SmsSignalInbox, type SmsReceivedSignal } from '@/lib/sms/notification';
import type { Notification } from '@/hooks/useNotifications';
export type DeviceNotice =
  | { key: string; kind: 'sms'; messageId: string; read: boolean }
  | { key: string; kind: 'reminder'; content: string; read: boolean };
/** One owner, no storage or world transport. Native reminder signals have no occurrence id:
 * suppress transport duplicates briefly, while allowing the next recurring occurrence. */
export class DeviceInbox {
  private readonly sms: SmsSignalInbox;
  private entries: DeviceNotice[] = [];
  private readonly reminders = new Map<string, number>();
  private serial = 0;
  constructor(ownerId: string) {
    this.sms = new SmsSignalInbox(ownerId);
  }
  receiveSms(signal: SmsReceivedSignal): boolean {
    const accepted = this.sms.accept(signal);
    if (!accepted) return false;
    this.push({
      key: 'sms:' + accepted.occurrence_id,
      kind: 'sms',
      messageId: accepted.message_id,
      read: false,
    });
    return true;
  }
  receiveReminder(n: Notification, now: number): boolean {
    if (n.type !== 'reminder' || !n.reminder_id || !Number.isFinite(now)) return false;
    const previous = this.reminders.get(n.reminder_id);
    if (previous !== undefined && now - previous < 5000) return false;
    this.reminders.delete(n.reminder_id);
    this.reminders.set(n.reminder_id, now);
    if (this.reminders.size > 128) this.reminders.delete(this.reminders.keys().next().value!);
    this.push({
      key: 'reminder:' + ++this.serial,
      kind: 'reminder',
      content: n.content.slice(0, 4000),
      read: false,
    });
    return true;
  }
  private push(n: DeviceNotice): void {
    this.entries = [n, ...this.entries].slice(0, 32);
  }
  read(key: string): void {
    this.entries = this.entries.map(n => (n.key === key ? { ...n, read: true } : n));
  }
  snapshot(): readonly DeviceNotice[] {
    return this.entries;
  }
}
