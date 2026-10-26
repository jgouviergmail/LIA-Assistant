/** Shared literal text and server-clock identity for both human audiences. */
import { z } from '@/lib/zod';
import { generateUUID } from '@/lib/utils';
export interface MailboxScope {
  epoch: string;
  controller: string;
}
export interface ServerClock {
  serverSeconds: number;
  receivedAt: number;
}
const uuid = z.uuid();
export function literalMessageText(value: string, maximum: number): string | null {
  if (Array.from(value).length > maximum || /[\uD800-\uDFFF]/u.test(value)) return null;
  const text = value.trim().normalize('NFC'),
    controls = text.replace(/[\n\t\u200c\u200d]/gu, '');
  return text &&
    !/[\p{Cc}\p{Cf}]/u.test(controls) &&
    new TextEncoder().encode(text).length <= maximum * 4
    ? text
    : null;
}
export function prepareMessageMetadata(scope: MailboxScope, clock: ServerClock, now: number) {
  const elapsed = now - clock.receivedAt;
  if (!Number.isFinite(elapsed + clock.serverSeconds) || elapsed < 0 || elapsed > 10000)
    throw new Error('world_message_clock');
  if (
    !uuid.safeParse(scope.epoch).success ||
    scope.controller.length < 16 ||
    scope.controller.length > 128
  )
    throw new Error('world_message_input');
  return { ...scope, id: generateUUID(), created_at: clock.serverSeconds + elapsed / 1000 };
}
