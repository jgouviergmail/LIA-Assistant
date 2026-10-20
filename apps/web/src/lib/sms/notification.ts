import { z } from '@/lib/zod';
const signal = z.object({
  type: z.literal('sms_received'),
  user_id: z.string().uuid(),
  message_id: z.string().uuid(),
  occurrence_id: z.string().uuid(),
});
export type SmsReceivedSignal = z.infer<typeof signal>;
/** Bounded, ephemeral replay suppression for one authenticated account lifetime.
 * Payload text and wire URLs are never projected into the signal.
 */
export class SmsSignalInbox {
  private readonly seen = new Set<string>();
  constructor(private readonly owner: string | undefined) {}
  accept(payload: unknown): SmsReceivedSignal | null {
    const parsed = signal.safeParse(payload);
    if (!parsed.success || !this.owner || parsed.data.user_id !== this.owner) return null;
    if (this.seen.has(parsed.data.occurrence_id)) return null;
    if (this.seen.size >= 512) {
      const first = this.seen.values().next().value;
      if (first) this.seen.delete(first);
    }
    this.seen.add(parsed.data.occurrence_id);
    return parsed.data;
  }
}
