/**
 * WorkboardCard — what on the board needs the person, on the dashboard.
 *
 * Four exact counts, each a link into the board narrowed to the very set it
 * counts; then the first tickets waiting on the person, each a link to the
 * ticket itself. A board with no open ticket is the empty state; a board with
 * open tickets and nothing waiting says so in one line.
 */

import { describe, it, expect } from 'vitest';
import { within } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { WorkboardCard } from '../WorkboardCard';
import type { CardSection, WorkboardData, WorkboardTicketItem } from '@/types/briefing';

const props = { isRefreshing: false, onRefresh: () => {}, staggerIndex: 0 };

function ticket(over: Partial<WorkboardTicketItem> = {}): WorkboardTicketItem {
  return {
    id: 't-1',
    title: 'Book the venue',
    status: 'waiting',
    due_at: null,
    overdue: false,
    ...over,
  };
}

function section(
  data: WorkboardData | null,
  status: CardSection['status'] = 'ok'
): CardSection<WorkboardData> {
  return {
    status,
    data,
    generated_at: '2026-10-03T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

function data(over: Partial<WorkboardData> = {}): WorkboardData {
  return { needs_me: 0, held_by_lia: 0, overdue: 0, open_total: 0, items: [], ...over };
}

/** The figure link whose visible label is `label`. */
function figure(label: string): HTMLElement {
  const glance = screen.getByRole('list', { name: 'settings.workboard.glance' });
  return within(glance).getByRole('link', { name: new RegExp(label) });
}

const OPEN =
  'status=idea&status=todo&status=in_progress&status=waiting&status=confirming&status=validating';

describe('WorkboardCard', () => {
  it('shows the four exact counts, each linking to the board narrowed to its set', () => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section(data({ needs_me: 5, held_by_lia: 2, overdue: 3, open_total: 12 }))}
      />
    );

    expect(figure('settings.workboard.tile_needs_me')).toHaveTextContent('5');
    expect(figure('settings.workboard.tile_needs_me')).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard'
    );
    expect(figure('settings.workboard.tile_lia')).toHaveTextContent('2');
    expect(figure('settings.workboard.tile_lia')).toHaveAttribute(
      'href',
      `/fr/dashboard/workboard?${OPEN}&assignee=lia`
    );
    expect(figure('settings.workboard.tile_overdue')).toHaveTextContent('3');
    expect(figure('settings.workboard.tile_overdue')).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard?overdue=1'
    );
    expect(figure('dashboard.briefing.cards.workboard.tile_open')).toHaveTextContent('12');
    expect(figure('dashboard.briefing.cards.workboard.tile_open')).toHaveAttribute(
      'href',
      `/fr/dashboard/workboard?${OPEN}`
    );
  });

  it('lists the tickets waiting on the person, each linking to the ticket', () => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section(
          data({
            needs_me: 2,
            open_total: 2,
            items: [
              ticket({ id: 'late-1', title: 'Pay the invoice', status: 'todo', overdue: true }),
              ticket({ id: 'ask-2', title: 'Answer LIA', status: 'confirming' }),
            ],
          })
        )}
      />
    );

    const waiting = screen.getByRole('list', { name: 'settings.workboard.tile_needs_me' });
    const rows = within(waiting).getAllByRole('link');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute('href', '/fr/dashboard/workboard/late-1');
    expect(rows[0]).toHaveTextContent('Pay the invoice');
    // A late ticket says it is late rather than naming its column.
    expect(rows[0]).toHaveTextContent('workboard.card.overdue');
    expect(rows[1]).toHaveAttribute('href', '/fr/dashboard/workboard/ask-2');
    expect(rows[1]).toHaveTextContent('workboard.columns.confirming');
    // Everything waiting is listed: no « more » link.
    expect(
      screen.queryByRole('link', { name: 'dashboard.briefing.cards.workboard.more' })
    ).not.toBeInTheDocument();
  });

  it('states what the short list leaves out, from the exact count', () => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section(data({ needs_me: 9, open_total: 9, items: [ticket()] }))}
      />
    );

    expect(
      screen.getByRole('link', { name: 'dashboard.briefing.cards.workboard.more' })
    ).toHaveAttribute('href', '/fr/dashboard/workboard');
  });

  it('says in one line that nothing waits when the open board needs nothing', () => {
    renderWithProviders(
      <WorkboardCard {...props} section={section(data({ held_by_lia: 3, open_total: 3 }))} />
    );

    expect(screen.getByText('settings.workboard.nothing_waiting')).toBeInTheDocument();
    expect(
      screen.queryByRole('list', { name: 'settings.workboard.tile_needs_me' })
    ).not.toBeInTheDocument();
  });

  it('shows the empty state for a board with no open ticket', () => {
    renderWithProviders(<WorkboardCard {...props} section={section(null, 'empty')} />);

    expect(screen.getByText('dashboard.briefing.cards.workboard.empty')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('is absent when the instance switched the workboard off', () => {
    renderWithProviders(<WorkboardCard {...props} section={section(null, 'not_configured')} />);

    expect(
      screen.queryByRole('region', { name: 'dashboard.briefing.cards.workboard.title' })
    ).not.toBeInTheDocument();
  });
});
