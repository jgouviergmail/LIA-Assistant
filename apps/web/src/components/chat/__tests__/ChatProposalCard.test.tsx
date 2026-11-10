/**
 * ChatProposalCard — the one habit proposal shown under the latest answer (ADR-375).
 *
 * The server chooses it and carries it in the answer's metadata
 * (`habit_proposal`); the page shows it under the LATEST answer only, never
 * while the surface is busy, never once decided here, and never from a value
 * that is not a proposal (the metadata is untyped JSON, read through one parser).
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { visibleProposal } from '@/hooks/useChatProposal';
import type { HabitProposal, ProposalDecisions } from '@/hooks/useHabitProposals';
import type { Message } from '@/types/chat';

import { ChatProposalCard } from '../ChatProposalCard';

const STAMP = { created_at: '2026-11-08T03:00:00Z', updated_at: '2026-11-08T03:00:00Z' };

const AUTOMATE: HabitProposal = {
  id: 'p-automate',
  kind: 'automate_need',
  key: 'weather',
  facts: {
    domain: 'weather',
    cadence: 'weekdays',
    weekday: null,
    hour: 7,
    minute: 30,
    distinct_days: 14,
    active_days: 22,
    part_of_day: 'morning',
    existing_routine: null,
  },
  ...STAMP,
};

const FIX: HabitProposal = {
  id: 'p-fix',
  kind: 'fix_routine',
  key: 'r-1',
  facts: { routine_id: 'r-1', routine_title: 'Matin', failures: 4, disabled: false },
  ...STAMP,
};

function answer(id: string, metadata: Record<string, unknown> = {}): Message {
  return { id, role: 'assistant', content: 'ok', timestamp: new Date(0), metadata };
}

function question(id: string): Message {
  return { id, role: 'user', content: 'météo ?', timestamp: new Date(0) };
}

const NONE_DECIDED: ReadonlySet<string> = new Set();

describe('visibleProposal — the latest answer only', () => {
  it('shows the proposal the latest answer carries', () => {
    const messages = [question('q'), answer('a', { habit_proposal: AUTOMATE })];
    expect(visibleProposal(messages, false, NONE_DECIDED)).toEqual(AUTOMATE);
  });

  it('reads every kind through the same parser', () => {
    const messages = [answer('a', { habit_proposal: FIX })];
    expect(visibleProposal(messages, false, NONE_DECIDED)).toEqual(FIX);
  });

  it('never shows an earlier answer’s proposal under a newer answer', () => {
    const messages = [answer('a1', { habit_proposal: AUTOMATE }), question('q'), answer('a2')];
    expect(visibleProposal(messages, false, NONE_DECIDED)).toBeNull();
  });

  it('disappears once the person writes again', () => {
    const messages = [answer('a', { habit_proposal: AUTOMATE }), question('q')];
    expect(visibleProposal(messages, false, NONE_DECIDED)).toBeNull();
  });

  it('waits while the surface is busy (streaming, history view)', () => {
    const messages = [answer('a', { habit_proposal: AUTOMATE })];
    expect(visibleProposal(messages, true, NONE_DECIDED)).toBeNull();
  });

  it('leaves at once when decided here', () => {
    const messages = [answer('a', { habit_proposal: AUTOMATE })];
    expect(visibleProposal(messages, false, new Set([AUTOMATE.id]))).toBeNull();
  });

  it('shows nothing in an empty conversation', () => {
    expect(visibleProposal([], false, NONE_DECIDED)).toBeNull();
  });
});

describe('visibleProposal — only a proposal is a proposal', () => {
  it.each<[string, unknown]>([
    ['a string', 'p-automate'],
    ['an unknown kind', { ...AUTOMATE, kind: 'shortcut' }],
    ['facts missing a field', { ...AUTOMATE, facts: { domain: 'weather' } }],
    ['facts of another kind', { ...FIX, kind: 'automate_need' }],
    ['no id', { ...AUTOMATE, id: undefined }],
  ])('ignores %s', (_label, value) => {
    const messages = [answer('a', { habit_proposal: value })];
    expect(visibleProposal(messages, false, NONE_DECIDED)).toBeNull();
  });
});

describe('ChatProposalCard', () => {
  function decisions(over: Partial<ProposalDecisions> = {}): ProposalDecisions {
    return { pending: null, decided: NONE_DECIDED, decide: vi.fn(), ...over };
  }

  it('is a named region holding the proposal’s sentence and its three decisions', () => {
    renderWithProviders(<ChatProposalCard proposal={AUTOMATE} decisions={decisions()} />);

    const card = screen.getByRole('region', { name: 'habits.proposals.chat_title' });
    expect(card).toHaveTextContent('habits.proposals.automate_need.text');
    for (const name of [
      'habits.proposals.automate_need.accept',
      'habits.proposals.later',
      'habits.proposals.never',
    ]) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
  });

  it('hands the decision to the same door as the inbox', async () => {
    const decide = vi.fn();
    const { user } = renderWithProviders(
      <ChatProposalCard proposal={AUTOMATE} decisions={decisions({ decide })} />
    );

    await user.click(screen.getByRole('button', { name: 'habits.proposals.later' }));

    expect(decide).toHaveBeenCalledWith(AUTOMATE, 'dismiss');
  });
});
