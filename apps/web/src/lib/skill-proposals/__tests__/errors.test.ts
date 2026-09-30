/** The refusals a skill proposal's card is told (ADR-327): a code it knows, or its own sentence. */
import { describe, expect, it } from 'vitest';

import { isProposalGone, proposalRefusalKey } from '../errors';

function refused(status: number, code?: string) {
  return { status, data: { detail: code ? { code } : 'not a coded refusal' } };
}

describe('proposalRefusalKey', () => {
  it('names a code the API sends', () => {
    expect(proposalRefusalKey(refused(409, 'skill_proposal_stale'))).toBe(
      'chat.skill_proposal.errors.skill_proposal_stale'
    );
  });

  it('leaves a code it does not know to the caller', () => {
    expect(proposalRefusalKey(refused(409, 'skill_library_name_taken'))).toBeNull();
    expect(proposalRefusalKey(new Error('network'))).toBeNull();
  });
});

describe('isProposalGone', () => {
  it('is the API saying the proposal no longer exists', () => {
    expect(isProposalGone(refused(404, 'skill_proposal_not_found'))).toBe(true);
  });

  it('is a bare 404 too', () => {
    expect(isProposalGone({ status: 404, data: {} })).toBe(true);
  });

  it('is never another refusal', () => {
    expect(isProposalGone(refused(503, 'skill_proposal_unavailable'))).toBe(false);
    expect(isProposalGone(refused(404, 'skill_proposal_stale'))).toBe(false);
    expect(isProposalGone(null)).toBe(false);
  });
});
