import type { LLMUsage } from '@/types/llm-usage';

/**
 * How the person writes their e-mails, as LIA learned it from their sent mail (ADR-383).
 * The shape of `GET /writing-style`, also answered by `PATCH /writing-style`.
 */
export interface WritingStyle {
  /** The person's switch: e-mails LIA writes follow the style. */
  enabled: boolean;
  /** How many of the latest sent e-mails a learning reads (the instance's setting). */
  mails_to_read: number;
  /** What was learned; null when nothing was (or nothing could be). */
  profile: string | null;
  /** How many sent e-mails it was learned from; null before any learning. */
  mails_read: number | null;
  /** When it was learned (ISO, UTC), at the person's request; null before any learning. */
  learned_at: string | null;
}

/**
 * How a learning the person asked for ended — `LearningOutcome` in
 * `domains/agents/emails/writing_style.py`, held equal by a backend test.
 * `superseded`: the style was forgotten or learned again meanwhile, so this learning
 * kept nothing — the person's later act stands.
 */
export type WritingStyleLearningOutcome =
  | 'learned'
  | 'too_few'
  | 'no_mailbox'
  | 'reconnect'
  | 'switched_off'
  | 'superseded';

/** The answer of `POST /writing-style/learn`: how the learning ended, and what it cost. */
export interface WritingStyleLearning {
  outcome: WritingStyleLearningOutcome;
  /** How many sent e-mails were read (0 when none was). */
  mails_read: number;
  /** What it cost; null when nothing was spent on it now. */
  usage: LLMUsage | null;
}
