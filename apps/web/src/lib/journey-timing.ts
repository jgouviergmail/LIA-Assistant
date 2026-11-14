/**
 * The chat's first-token timing (spec 2026-10-21 O2).
 *
 * From the person's send to the first answer token: marked where a NEW stream
 * starts (never a resumed run), read once on the first token chunk — a progress
 * step is never a first token. Each discussion owns its clock.
 */
import { trackClientTiming } from '@/lib/product-telemetry';

export function createChatTurnTiming() {
  let startedAt: number | null = null;

  /** The person sent a message: the wait for its first token starts now. */
  function markChatTurnStarted(): void {
    startedAt = performance.now();
  }

  /** A stream this module did not start (a resumed run): nothing is measured. */
  function clearChatTurnTiming(): void {
    startedAt = null;
  }

  /** The first answer token arrived: emit the wait once, then forget it. */
  function noteChatFirstToken(): void {
    if (startedAt === null) return;
    const seconds = (performance.now() - startedAt) / 1000;
    startedAt = null;
    trackClientTiming('chat_first_token', seconds);
  }

  return { markChatTurnStarted, clearChatTurnTiming, noteChatFirstToken };
}
