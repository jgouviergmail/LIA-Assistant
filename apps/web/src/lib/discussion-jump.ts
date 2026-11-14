/**
 * A jump to a message of ANOTHER discussion, carried across the switch.
 *
 * Each discussion mounts its own chat view, so the history search that found a
 * message is gone once the discussion holding it is on screen. The search leaves
 * the jump here before asking for the switch; the arriving view takes it once its
 * history is loaded. A jump is taken by the discussion it names and by no other,
 * once, and never after `DISCUSSION_JUMP_TTL_MS`: a discussion opened later by
 * another path does not inherit an old intention.
 */

import { DISCUSSION_JUMP_TTL_MS } from '@/lib/constants';

export interface DiscussionJump {
  /** The discussion that holds the message. */
  conversationId: string;
  /** The message's instant: the arriving view shows the page ending at it. */
  createdAt: string;
  /** The words searched, marked in the arriving view. */
  term: string;
}

let pending: { jump: DiscussionJump; at: number } | null = null;

/** Leave a jump for the discussion about to open; it replaces any earlier one. */
export function requestDiscussionJump(jump: DiscussionJump, now: number = Date.now()): void {
  pending = { jump, at: now };
}

/**
 * The jump left for this discussion, if any — taken: it is gone afterwards.
 *
 * A jump for another discussion is left alone; a stale one is dropped.
 */
export function takeDiscussionJump(
  conversationId: string,
  now: number = Date.now()
): DiscussionJump | null {
  const held = pending;
  if (!held) return null;
  if (now - held.at > DISCUSSION_JUMP_TTL_MS) {
    pending = null;
    return null;
  }
  if (held.jump.conversationId !== conversationId) return null;
  pending = null;
  return held.jump;
}

/**
 * Forget a waiting jump between tests, which share this module's state.
 *
 * Production never needs to: a jump is replaced by the next one and expires.
 */
export function resetDiscussionJumpForTests(): void {
  pending = null;
}
