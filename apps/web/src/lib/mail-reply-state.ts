import { z } from '@/lib/zod';

/**
 * Where a mail stands in its conversation, as the mailbox said when it was listed (ADR-379).
 *
 * The API ships the whole annotation beside the mail (`core/mail_reply_state.py`); a
 * screen reads the STATUS alone, so the reader requires no more than it reads. An
 * unknown version or status reads as no state at all: a mark nobody understands is
 * never drawn.
 */
const replyState = z.object({
  version: z.literal('mail-reply-state-v1'),
  status: z.enum(['answered', 'answer_drafted', 'unanswered', 'reply_received', 'awaiting_reply']),
});
export type ReplyState = z.infer<typeof replyState>;

/** What stays true once observed: an answer that was sent stays sent. */
export type SettledReplyStatus = Extract<ReplyState['status'], 'answered' | 'reply_received'>;

/**
 * The status a SCREEN may show of a stored reply state.
 *
 * Only the two facts are shown. « Nobody answered yet » and « a draft waits » are the
 * reading of a moment: a cached card or an archived answer would go on stating them
 * after they stopped being true (the server's `DURABLE_STATUSES`).
 */
export function settledReplyStatus(value: unknown): SettledReplyStatus | null {
  const parsed = replyState.safeParse(value);
  if (!parsed.success) return null;
  const { status } = parsed.data;
  return status === 'answered' || status === 'reply_received' ? status : null;
}
