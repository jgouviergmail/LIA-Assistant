/**
 * The refusals the skill proposal API names (`detail.code`), as the sentence to show (ADR-327).
 *
 * Every code the API sends has a sentence in the six languages (a backend
 * guard pins the pair, `test_proposal_errors.py`). A refusal the API named
 * with no code the card knows falls back to the caller's generic sentence.
 */
import { getApiErrorFields, getApiErrorStatus } from '@/lib/api-error';

const PREFIX = 'chat.skill_proposal.errors';

/** Every code the API may answer the card with. */
export const PROPOSAL_REFUSAL_CODES: ReadonlySet<string> = new Set([
  'skill_proposal_not_found',
  'skill_proposal_stale',
  'skill_proposal_busy',
  'skill_proposal_disabled',
  'skill_proposal_name_taken',
  'skill_proposal_quota_reached',
  'skill_proposal_invalid',
  'skill_proposal_unavailable',
]);

/**
 * The i18n key of a refusal's sentence.
 *
 * @param error - Anything a `catch` block (or a query) received.
 * @returns The sentence key, or `null` when the API named no code the card knows.
 */
export function proposalRefusalKey(error: unknown): string | null {
  const code = getApiErrorFields(error)?.code;
  return typeof code === 'string' && PROPOSAL_REFUSAL_CODES.has(code) ? `${PREFIX}.${code}` : null;
}

/**
 * Whether the proposal no longer exists (expired, replaced by newer ones, or never this account's).
 *
 * @param error - The read's error.
 * @returns True for the API's `not_found` refusal, or a bare 404.
 */
export function isProposalGone(error: unknown): boolean {
  const code = getApiErrorFields(error)?.code;
  return (
    code === 'skill_proposal_not_found' || (code === undefined && getApiErrorStatus(error) === 404)
  );
}
