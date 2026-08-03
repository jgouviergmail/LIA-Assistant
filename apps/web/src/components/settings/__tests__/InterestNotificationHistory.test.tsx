/**
 * The interest notifications this account received.
 *
 * Same card as the proactive history (`NotificationHistoryList`), deliberately:
 * the two panels answer the same question — "what was I interrupted with, and
 * was it worth it?" — and must not drift into two visual languages.
 *
 * Two differences of vocabulary, both load-bearing here: there is no priority
 * to state (an interest nudge is never urgent), and `content` is optional
 * because the audit table only started keeping the message on 2026-08-03.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { InterestNotificationHistory } from '../InterestNotificationHistory';
import type { InterestNotification } from '@/hooks/useInterestNotificationHistory';

function notification(over: Partial<InterestNotification> = {}): InterestNotification {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    created_at: '2026-08-01T09:30:00Z',
    content: 'Trois articles sur la fusion nucléaire cette semaine.',
    source: 'perplexity',
    topic: 'fusion nucléaire',
    user_feedback: null,
    ...over,
  };
}

function makeProps(
  over: Partial<React.ComponentProps<typeof InterestNotificationHistory>> = {}
): React.ComponentProps<typeof InterestNotificationHistory> {
  return {
    notifications: [notification()],
    total: 1,
    firstLoad: false,
    loading: false,
    error: null,
    locale: 'fr-FR',
    ...over,
  };
}

describe('InterestNotificationHistory', () => {
  it('shows the message, the interest and the provider', () => {
    renderWithProviders(<InterestNotificationHistory {...makeProps()} />);

    expect(
      screen.getByText('Trois articles sur la fusion nucléaire cette semaine.')
    ).toBeInTheDocument();
    expect(screen.getByText('fusion nucléaire')).toBeInTheDocument();
    expect(screen.getByText('interests.history.source_perplexity')).toBeInTheDocument();
  });

  it('renders a row that predates the content column without inventing one', () => {
    // A hash does not invert: there is nothing to backfill, and a summary made
    // up here would be the one thing worse than an absent one.
    renderWithProviders(
      <InterestNotificationHistory {...makeProps({ notifications: [notification({ content: null })] })} />
    );

    expect(screen.getByText('fusion nucléaire')).toBeInTheDocument();
    expect(screen.queryByText(/fusion nucléaire cette semaine/)).not.toBeInTheDocument();
  });

  it('keeps a notification whose interest has since been deleted', () => {
    // `interest_id` is nullable. Dropping the row would hide part of the very
    // audit the reader opened the panel for.
    renderWithProviders(
      <InterestNotificationHistory {...makeProps({ notifications: [notification({ topic: null })] })} />
    );

    expect(
      screen.getByText('Trois articles sur la fusion nucléaire cette semaine.')
    ).toBeInTheDocument();
    expect(screen.getByText('interests.history.source_perplexity')).toBeInTheDocument();
  });

  it('never shows a raw i18n key for a provider it does not know', () => {
    renderWithProviders(
      <InterestNotificationHistory
        {...makeProps({ notifications: [notification({ source: 'newsapi' })] })}
      />
    );

    expect(screen.queryByText(/interests\.history\.source_/)).not.toBeInTheDocument();
    expect(screen.getByText('newsapi')).toBeInTheDocument();
  });

  it('states the whole set next to the page, never the page alone', () => {
    renderWithProviders(<InterestNotificationHistory {...makeProps({ total: 57 })} />);

    expect(screen.getByText('interests.history.count')).toBeInTheDocument();
  });

  it('says the fetch failed rather than "nothing yet"', () => {
    // Checked BEFORE emptiness: an error rendered as an empty history tells
    // the reader LIA has been silent, which may be false.
    renderWithProviders(
      <InterestNotificationHistory
        {...makeProps({ notifications: undefined, error: new Error('boom') })}
      />
    );

    expect(screen.getByRole('alert')).toHaveTextContent('interests.history.error');
  });

  it('says so plainly when nothing has been sent yet', () => {
    renderWithProviders(<InterestNotificationHistory {...makeProps({ notifications: [], total: 0 })} />);

    expect(screen.getByText('interests.history.empty')).toBeInTheDocument();
  });

  it('shows a spinner on the first load only', () => {
    const { container } = renderWithProviders(
      <InterestNotificationHistory {...makeProps({ notifications: undefined, firstLoad: true })} />
    );

    expect(container.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it('announces a refresh instead of unmounting the list', () => {
    // A refetch keeps the rows on screen; `aria-busy` is what tells a screen
    // reader something is happening.
    renderWithProviders(<InterestNotificationHistory {...makeProps({ loading: true })} />);

    expect(screen.getByRole('list')).toHaveAttribute('aria-busy', 'true');
  });

  it('carries no priority badge — an interest nudge is never urgent', () => {
    renderWithProviders(<InterestNotificationHistory {...makeProps()} />);

    expect(screen.queryByText(/priority_/)).not.toBeInTheDocument();
  });

  it('puts the interest in the badge slot, where the proactive card puts its priority', () => {
    // The two histories share a card and must READ the same. The proactive row
    // opens with date + coloured badge + verdict; leaving that slot empty made
    // the interest row visibly lighter than its neighbour on the same page.
    // Priority has no equivalent here, but "what this was about" does.
    const { container } = renderWithProviders(<InterestNotificationHistory {...makeProps()} />);

    const badge = container.querySelector('.uppercase');
    expect(badge, 'the badge slot must be filled').not.toBeNull();
    expect(badge).toHaveTextContent('fusion nucléaire');
  });

  it('leaves the slot empty rather than inventing one when the interest is gone', () => {
    const { container } = renderWithProviders(
      <InterestNotificationHistory {...makeProps({ notifications: [notification({ topic: null })] })} />
    );

    expect(container.querySelector('.uppercase')).toBeNull();
  });

  it('stops repeating the interest as a chip once it is the badge', () => {
    renderWithProviders(<InterestNotificationHistory {...makeProps()} />);

    // Saying it twice on a two-line card is noise, not emphasis.
    expect(screen.getAllByText('fusion nucléaire')).toHaveLength(1);
  });
});
