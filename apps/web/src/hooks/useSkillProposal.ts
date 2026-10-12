/**
 * A skill the chat wrote, as its card reads and installs it (ADR-327).
 *
 * The model only PROPOSES a skill; the card's Install button is the one way
 * it enters the person's skills. A refusal reaches the caller as the
 * `ApiError` whose `detail.code` `lib/skill-proposals/errors.ts` turns into a
 * sentence.
 */
import { useCallback } from 'react';

import apiClient from '@/lib/api-client';
import type { SkillProposal } from '@/lib/skill-proposals/types';
import { useAuth } from './useAuth';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';

import { useApplicationAccountQuery } from './useApplicationAccountQuery';

const BASE = '/skill-proposals';

/**
 * The proposal, with its files while it may still be installed.
 *
 * @param proposalId - The proposal's id.
 * @param enabled - False for a card that knows its proposal is gone (its
 *   deadline passed): a history page may hold many, and none is worth a call.
 */
export function useSkillProposal(proposalId: string, enabled = true) {
  const query = useApplicationAccountQuery<SkillProposal>(
    `${BASE}/${encodeURIComponent(proposalId)}`,
    'SkillProposal',
    enabled
  );
  return { ...query, refetch: query.refetchVerified };
}

/** The card's one act: install the proposal. The caller owns its busy state. */
export function useSkillProposalActions() {
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const install = useCallback(
    async (proposalId: string) => {
      if (!isCurrent()) throw new Error('Skill proposal account is no longer current');
      return apiClient.post<SkillProposal>(`${BASE}/${encodeURIComponent(proposalId)}/install`);
    },
    [isCurrent]
  );
  return { install };
}
