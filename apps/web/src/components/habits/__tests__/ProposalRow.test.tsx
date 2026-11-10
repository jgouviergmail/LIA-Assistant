/**
 * One habit proposal (ADR-375): its sentence is built from FACTS in the
 * reader's language, its accept button says what accepting does, and a
 * decision is single-flight, navigates when the proposal opens a screen, and
 * says in words why an act was refused.
 */

import { useState } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { postMock, push, toast } = vi.hoisted(() => ({
  postMock: vi.fn(),
  push: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post: postMock },
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
    i18n: { language: 'fr' },
  }),
}));

import { ApiError } from '@/lib/api-client';
import {
  useProposalDecisions,
  type AutomateNeedFacts,
  type FixRoutineFacts,
  type HabitProposal,
} from '@/hooks/useHabitProposals';

import { ProposalList, ProposalRow, proposalCopy } from '../ProposalRow';

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}|${JSON.stringify(opts)}` : key;

const STAMP = { created_at: '2026-11-08T03:00:00Z', updated_at: '2026-11-08T03:00:00Z' };

function automate(over: Partial<AutomateNeedFacts> = {}): HabitProposal {
  return {
    id: 'p-automate',
    kind: 'automate_need',
    key: 'weather',
    facts: {
      domain: 'weather',
      cadence: 'weekly',
      weekday: 6,
      hour: 7,
      minute: 30,
      distinct_days: 14,
      active_days: 22,
      part_of_day: 'morning',
      existing_routine: null,
      ...over,
    },
    ...STAMP,
  };
}

function fix(over: Partial<FixRoutineFacts> = {}): HabitProposal {
  return {
    id: 'p-fix',
    kind: 'fix_routine',
    key: 'r-1',
    facts: { routine_id: 'r-1', routine_title: 'Matin', failures: 4, disabled: false, ...over },
    ...STAMP,
  };
}

const FIX = fix();

const CONNECT: HabitProposal = {
  id: 'p-connect',
  kind: 'connect_source',
  key: 'contacts',
  facts: { category: 'contacts', domain: 'contact', days: 5 },
  ...STAMP,
};

beforeEach(() => {
  postMock.mockReset().mockResolvedValue({});
  push.mockReset();
  for (const spy of Object.values(toast)) spy.mockReset();
});

describe('the sentence is built from facts', () => {
  it('a weekly need names its weekday, its time and its basis', () => {
    const copy = proposalCopy(t, 'fr', automate());
    // An unknown domain reads raw, never as a key path: hence the default value.
    expect(copy.text).toContain(
      'habits.proposals.domain.weather|{\\"defaultValue\\":\\"weather\\"}'
    );
    expect(copy.text).toContain('"days":14,"active":22');
    expect(copy.text).toContain('habits.proposals.schedule.weekly|{\\"day\\":\\"dimanche\\"}');
    expect(copy.text).toContain('"time":"07:30"');
    expect(copy.detail).toBeNull();
    expect(copy.accept).toBe('habits.proposals.automate_need.accept');
  });

  it('cites the routine that already reads it, at its own time', () => {
    const copy = proposalCopy(
      t,
      'fr',
      automate({ existing_routine: { id: 'r-9', title: 'Soir', hour: 18, minute: 0 } })
    );
    expect(copy.detail).toBe(
      'habits.proposals.automate_need.existing|{"title":"Soir","time":"18:00"}'
    );
  });

  it('a move says from when and to when, and its button says where', () => {
    const copy = proposalCopy(t, 'fr', {
      id: 'p-shift',
      kind: 'shift_routine',
      key: 'r-1',
      facts: {
        routine_id: 'r-1',
        routine_title: 'Matin',
        from_hour: 7,
        from_minute: 15,
        hour: 9,
        minute: 30,
        manual_runs: 4,
        manual_days: 3,
      },
      ...STAMP,
    });
    expect(copy.text).toContain('"from":"07:15"');
    expect(copy.accept).toBe('habits.proposals.shift_routine.accept|{"time":"09:30"}');
  });

  it('a routine the system switched off is said apart from one that fails', () => {
    const failing = proposalCopy(t, 'fr', FIX);
    const disabled = proposalCopy(t, 'fr', fix({ disabled: true }));
    expect(failing.text).toMatch(/^habits\.proposals\.fix_routine\.text_failing\|/);
    expect(disabled.text).toMatch(/^habits\.proposals\.fix_routine\.text_disabled\|/);
  });

  it('a window is written as two clock ranges', () => {
    const copy = proposalCopy(t, 'fr', {
      id: 'p-window',
      kind: 'extend_notification_window',
      key: 'heartbeat',
      facts: { start: 9, end: 21, new_start: 7, new_end: 23, outside_days: 9, outside_share: 0.31 },
      ...STAMP,
    });
    expect(copy.text).toContain('"window":"09:00–21:00"');
    expect(copy.accept).toBe(
      'habits.proposals.extend_notification_window.accept|{"new_window":"07:00–23:00"}'
    );
  });

  it('a missing connector names the domain asked and the category to connect', () => {
    const copy = proposalCopy(t, 'fr', CONNECT);
    expect(copy.text).toContain('habits.proposals.domain.contact|');
    expect(copy.text).toContain('habits.proposals.category.contacts|');
  });
});

/** The inbox in miniature: the decisions above, the rows below. */
function Inbox({ proposals }: { proposals: HabitProposal[] }) {
  const [decided, setDecided] = useState(0);
  const decisions = useProposalDecisions({ lng: 'fr', onDecided: () => setDecided(n => n + 1) });
  return (
    <>
      <p>decided:{decided}</p>
      <ProposalList
        proposals={proposals.filter(proposal => !decisions.decided.has(proposal.id))}
        decisions={decisions}
      />
    </>
  );
}

describe('a decision', () => {
  it('posts the verdict once, confirms an act, and leaves the list', async () => {
    const { user } = renderWithProviders(<Inbox proposals={[automate()]} />);
    await user.click(screen.getByRole('button', { name: 'habits.proposals.automate_need.accept' }));
    await waitFor(() => expect(screen.getByText('decided:1')).toBeInTheDocument());
    expect(postMock).toHaveBeenCalledExactlyOnceWith('/habits/proposals/p-automate/accept');
    expect(toast.success).toHaveBeenCalledWith('habits.proposals.automate_need.done');
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'habits.proposals.later' })).toBeNull();
  });

  it.each([
    [FIX, '/fr/dashboard/settings?section=scheduled-actions'],
    [CONNECT, '/fr/dashboard/settings?section=connectors'],
  ])('opens the screen a proposal points at', async (proposal, href) => {
    const { user } = renderWithProviders(<ProposalRowHarness proposal={proposal} />);
    await user.click(
      screen.getByRole('button', { name: `habits.proposals.${proposal.kind}.accept` })
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith(href));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('a proposal decided elsewhere leaves the list and says so', async () => {
    postMock.mockRejectedValue(
      new ApiError('conflict', 409, { detail: { error_code: 'PROPOSAL_NOT_OPEN' } })
    );
    const { user } = renderWithProviders(<Inbox proposals={[automate()]} />);
    await user.click(screen.getByRole('button', { name: 'habits.proposals.later' }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('habits.proposals.not_open'));
    expect(screen.getByText('decided:1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'habits.proposals.later' })).toBeNull();
  });

  it('a proposal shown before learning was switched off leaves and says why, never « try again »', async () => {
    // The chat card outlives the switch: it is archived with the answer.
    postMock.mockRejectedValue(
      new ApiError('forbidden', 403, { detail: { error_code: 'FEATURE_DISABLED' } })
    );
    const { user } = renderWithProviders(<Inbox proposals={[automate()]} />);
    await user.click(screen.getByRole('button', { name: 'habits.proposals.automate_need.accept' }));
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith('notifications_hub.sections.offers.learning_off')
    );
    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.getByText('decided:1')).toBeInTheDocument();
  });

  it('any other failure keeps the proposal and says the decision was not saved', async () => {
    postMock.mockRejectedValue(new ApiError('boom', 500, { detail: 'boom' }));
    const { user } = renderWithProviders(<Inbox proposals={[automate()]} />);
    await user.click(screen.getByRole('button', { name: 'habits.proposals.never' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('habits.proposals.error'));
    expect(screen.getByText('decided:0')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'habits.proposals.never' })).not.toHaveAttribute(
      'aria-disabled'
    );
  });
});

function ProposalRowHarness({ proposal }: { proposal: HabitProposal }) {
  const decisions = useProposalDecisions({ lng: 'fr', onDecided: () => undefined });
  return <ProposalRow proposal={proposal} decisions={decisions} />;
}
