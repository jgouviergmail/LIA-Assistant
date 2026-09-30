/**
 * A skill the chat wrote, waiting for the person's click (ADR-327).
 *
 * The model only PROPOSES a skill; the card under the answer shows what it
 * is and its Install button is the one way it enters the person's skills.
 * `SkillProposalCard` is what the answer carries (the done chunk and the
 * archived row share it); `SkillProposal` is what the card reads before the
 * click, with the files' contents while it may still be installed.
 */

/** One file of the package: its path and UTF-8 size. */
export interface SkillProposalFile {
  path: string;
  size: number;
}

/** What a replacement does to the person's installed skill. */
export interface SkillProposalChanges {
  added: string[];
  modified: string[];
  /** Text files whose content the install loses. */
  removed: string[];
}

/** The card under the answer — the same shape live and after a reload. */
export interface SkillProposalCard {
  id: string;
  name: string;
  description: string;
  /** Whether it replaces a skill of the person's own. */
  replaces: boolean;
  /** The package, manifest first. */
  files: SkillProposalFile[];
  /** What a replacement changes; null for a new skill. */
  changes: SkillProposalChanges | null;
  /** ISO-8601 instant after which it can no longer be installed. */
  expires_at: string;
}

/** A proposal as the card reads it (`GET /skill-proposals/{id}`). */
export interface SkillProposal extends Omit<SkillProposalCard, 'files'> {
  status: 'pending' | 'installed';
  /** Each file, with its text while the proposal is pending (null once installed). */
  files: Array<SkillProposalFile & { content: string | null }>;
}
