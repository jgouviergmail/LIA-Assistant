/**
 * How the person writes their e-mails, as LIA learned it from their sent mail (ADR-383).
 * The shape of `GET /writing-style`, also answered by `PATCH /writing-style`.
 */
export interface WritingStyle {
  /** The person's switch: e-mails LIA writes follow the style. */
  enabled: boolean;
  /** What was learned; null when nothing was (or nothing could be). */
  profile: string | null;
  /** How many sent e-mails it was learned from; null before any learning. */
  mails_read: number | null;
  /** When it was learned (ISO, UTC); null before any learning. */
  learned_at: string | null;
  /** From when the next e-mail LIA writes learns it again (ISO, UTC). */
  renews_at: string | null;
}
