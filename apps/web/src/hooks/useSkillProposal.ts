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

import { useApiQuery } from './useApiQuery';

const BASE = '/skill-proposals';

/**
 * The proposal, with its files while it may still be installed.
 *
 * @param proposalId - The proposal's id.
 * @param enabled - False for a card that knows its proposal is gone (its
 *   deadline passed): a history page may hold many, and none is worth a call.
 */
export function useSkillProposal(proposalId: string, enabled = true) {
  return useApiQuery<SkillProposal>(`${BASE}/${encodeURIComponent(proposalId)}`, {
    componentName: 'SkillProposal',
    enabled,
  });
}

/** The card's one act: install the proposal. The caller owns its busy state. */
export function useSkillProposalActions() {
  const install = useCallback(
    (proposalId: string) =>
      apiClient.post<SkillProposal>(`${BASE}/${encodeURIComponent(proposalId)}/install`),
    []
  );
  return { install };
}
