'use client';

/**
 * The habit proposal the chat shows under its latest answer (ADR-375).
 *
 * One hook for the chat page: which proposal the latest answer carries (none
 * while the surface is busy, none once decided here) and the decisions on it,
 * through the inbox's own door (`useProposalDecisions`). Decided here, the
 * card leaves at once and the focus it held returns to the composer.
 */

import { useMemo } from 'react';

import {
  habitProposalOf,
  useProposalDecisions,
  type HabitProposal,
  type ProposalDecisions,
} from '@/hooks/useHabitProposals';
import type { Message } from '@/types/chat';

/**
 * Visibility rule (pure, exported for tests): the proposal the latest answer
 * carries, unless the surface is busy or the person already decided it here.
 */
export function visibleProposal(
  messages: Message[],
  blocked: boolean,
  decided: ReadonlySet<string>
): HabitProposal | null {
  if (blocked) return null;
  const last = messages[messages.length - 1];
  if (!last || last.role !== 'assistant') return null;
  const proposal = habitProposalOf(last.metadata?.habit_proposal);
  return proposal && !decided.has(proposal.id) ? proposal : null;
}

export interface ChatProposal {
  /** The proposal to show, already filtered — or null. */
  proposal: HabitProposal | null;
  decisions: ProposalDecisions;
}

/** Hand the focus back to the composer once the card it rested on is gone. */
function focusComposer(restoreFocus: boolean): void {
  if (restoreFocus) document.querySelector<HTMLElement>('[data-chat-composer]')?.focus();
}

export function useChatProposal(messages: Message[], busy: boolean, lng: string): ChatProposal {
  const decisions = useProposalDecisions({ lng, onDecided: focusComposer });
  const proposal = useMemo(
    () => visibleProposal(messages, busy, decisions.decided),
    [messages, busy, decisions.decided]
  );
  return { proposal, decisions };
}
