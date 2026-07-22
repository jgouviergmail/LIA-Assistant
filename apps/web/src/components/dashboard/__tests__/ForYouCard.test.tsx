/**
 * « For you » card (P15, interdomain program Lot 4).
 *
 * Aggregates the commitments ledger (ADR-139) + automations digest (ADR-140).
 * Loop rows are real labelled buttons opening the chat prefilled with a
 * direction-aware intent (QW-9 `?draft=` pattern).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ForYouCard } from '../cards/ForYouCard';
import type { CardSection, ForYouData } from '@/types/briefing';

const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

function section(data: ForYouData | null, status = 'ok'): CardSection<ForYouData> {
  return {
    status: status as CardSection<ForYouData>['status'],
    data,
    generated_at: '2026-07-22T08:00:00Z',
    error_code: null,
    error_message: null,
  };
}

const cardProps = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };

const fullData: ForYouData = {
  open_loops: [
    {
      id: 'l1',
      subject: 'rappeler le plombier',
      counterparty: 'le plombier',
      direction: 'user_owes',
      due_hint: null,
      days_open: 3,
    },
    {
      id: 'l2',
      subject: 'devis de Marie',
      counterparty: 'Marie',
      direction: 'waiting_on_other',
      due_hint: '2026-07-25T18:00:00Z',
      days_open: 9,
    },
  ],
  recent_automations: [
    {
      id: 'a1',
      title: 'Revue de presse IA',
      executed_at: '2026-07-22T06:00:00Z',
      next_trigger_at: null,
      next_trigger_local: null,
    },
  ],
  next_automation: {
    id: 'a2',
    title: 'Météo du matin',
    executed_at: null,
    next_trigger_at: '2026-07-23T06:00:00Z',
    next_trigger_local: '06:00 demain',
  },
};

describe('ForYouCard', () => {
  beforeEach(() => {
    push.mockClear();
  });

  it('renders loops with direction-aware intents and opens the chat on click', () => {
    render(<ForYouCard {...cardProps} section={section(fullData)} />);

    const owed = screen.getByRole('button', {
      name: /intents\.loop_owed\|subject=rappeler le plombier/,
    });
    fireEvent.click(owed);
    expect(push).toHaveBeenCalledWith(expect.stringContaining('/fr/dashboard/chat?draft='));
    expect(push.mock.calls[0][0]).toContain(encodeURIComponent('rappeler le plombier'));

    // Waiting-direction loop gets the waiting intent
    expect(
      screen.getByRole('button', { name: /intents\.loop_waiting\|subject=devis de Marie/ })
    ).toBeInTheDocument();
  });

  it('renders the automations digest with the precise next execution time', () => {
    render(<ForYouCard {...cardProps} section={section(fullData)} />);

    expect(screen.getByText('Revue de presse IA')).toBeInTheDocument();
    expect(screen.getByText('dashboard.briefing.cards.for_you.ran_recently')).toBeInTheDocument();
    expect(screen.getByText('Météo du matin')).toBeInTheDocument();
    // Precise backend-formatted time replaces the vague "next up" label
    expect(screen.getByText('06:00 demain')).toBeInTheDocument();
    expect(screen.queryByText('dashboard.briefing.cards.for_you.next_up')).not.toBeInTheDocument();
  });

  it('falls back to the next-up label when no local time is provided', () => {
    const data = {
      ...fullData,
      next_automation: {
        id: 'a2',
        title: 'Météo du matin',
        executed_at: null,
        next_trigger_at: '2026-07-23T06:00:00Z',
        next_trigger_local: null,
      },
    };
    render(<ForYouCard {...cardProps} section={section(data)} />);

    expect(screen.getByText('dashboard.briefing.cards.for_you.next_up')).toBeInTheDocument();
  });

  it('is hidden entirely when the section is not configured', () => {
    const { container } = render(
      <ForYouCard {...cardProps} section={section(null, 'not_configured')} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the empty state when the section is empty', () => {
    render(<ForYouCard {...cardProps} section={section(null, 'empty')} />);
    expect(screen.getByText('dashboard.briefing.cards.for_you.empty')).toBeInTheDocument();
  });
});
