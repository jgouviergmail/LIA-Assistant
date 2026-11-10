'use client';

/**
 * ChatProposalCard — the one habit proposal shown under the latest answer (ADR-375).
 *
 * The server decides which proposal an answer shows — at most one, by code,
 * never by a model — and carries it on the chips' two roads: the archived
 * answer's metadata and its `done` chunk, under `habit_proposal`. The card is
 * the inbox's row (`ProposalRow`): the sentence built from facts in the
 * reader's language and the same three decisions, through the same door.
 *
 * Like the chips, it belongs to the LATEST answer only and waits while the
 * surface is busy; deciding it here hides it at once (`useChatProposal`).
 * Whether it may take the slot is the arbiter's call (`lib/chat-surfaces`): it
 * yields to a pending approval and to the usage wall, and the chips yield to it.
 */

import { Lightbulb } from '@/lib/icons';
import { useTranslation } from 'react-i18next';

import { ProposalRow } from '@/components/habits/ProposalRow';
import type { HabitProposal, ProposalDecisions } from '@/hooks/useHabitProposals';

export interface ChatProposalCardProps {
  proposal: HabitProposal;
  /** The page's decisions: one in flight at a time, decided ones hidden. */
  decisions: ProposalDecisions;
}

export function ChatProposalCard({ proposal, decisions }: ChatProposalCardProps) {
  const { t } = useTranslation();
  const title = t('habits.proposals.chat_title');
  return (
    <section
      aria-label={title}
      className="mx-auto mb-3 w-full max-w-4xl rounded-xl border border-primary/30 bg-card/70 px-4 py-3 shadow-sm backdrop-blur-sm lg:max-w-chat-composer"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Lightbulb className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="mb-1 text-sm font-semibold text-foreground">{title}</p>
          <ProposalRow proposal={proposal} decisions={decisions} compact />
        </div>
      </div>
    </section>
  );
}
