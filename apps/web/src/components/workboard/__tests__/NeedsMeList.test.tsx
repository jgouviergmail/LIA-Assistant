/**
 * The hub's ticket rows.
 *
 * Every row is a LINK to the ticket's own URL, which is the same path the
 * backend puts in a notification — the hub must not invent a second way to
 * reach a ticket. And a ticket here is one that NEEDS the person, so the two
 * reasons it can be here (a stopped run, an overdue date) have to be legible
 * without opening it.
 */
import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { NeedsMeList } from '@/components/workboard/NeedsMeList';
import type { TicketRow } from '@/types/workboard';

function ticket(overrides: Partial<TicketRow> & { id: string }): TicketRow {
  return {
    owner_user_id: 'me',
    parent_id: null,
    title: `Ticket ${overrides.id}`,
    description: null,
    status: 'waiting',
    priority: 'medium',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: 'me',
    position: 0,
    follow_owner: false,
    follow_assignee: false,
    created_by: 'user',
    status_changed_at: '2026-09-09T10:00:00Z',
    run_count: 0,
    run_claimed_at: null,
    last_run_at: null,
    last_run_outcome: null,
    last_run_error: null,
    last_run_tokens_in: null,
    last_run_tokens_out: null,
    last_run_cost_eur: null,
    created_at: '2026-09-09T10:00:00Z',
    execution_mode: 'react',
    total_tokens_in: 0,
    total_tokens_out: 0,
    total_tokens_cache: 0,
    total_google_requests: 0,
    total_cost_eur: 0,
    updated_at: '2026-09-09T10:00:00Z',
    ...overrides,
  };
}

describe('the rows', () => {
  it('links each ticket at the URL a notification would use', () => {
    renderWithProviders(<NeedsMeList tickets={[ticket({ id: 'abc' })]} lng="fr" />);

    expect(screen.getByRole('link', { name: /Ticket abc/ })).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard/abc'
    );
  });

  it('says which column it is waiting in', () => {
    renderWithProviders(
      <NeedsMeList tickets={[ticket({ id: 'a', status: 'waiting' })]} lng="fr" />
    );

    expect(screen.getByText('workboard.columns.waiting')).toBeInTheDocument();
  });

  it('marks an overdue ticket, and shows a due date that has not passed', () => {
    renderWithProviders(
      <NeedsMeList
        tickets={[
          ticket({ id: 'late', due_at: '2020-01-01T00:00:00Z', status: 'todo' }),
          ticket({ id: 'soon', due_at: '2999-01-01T00:00:00Z', status: 'todo' }),
        ]}
        lng="fr"
      />
    );

    expect(screen.getByText('workboard.card.overdue')).toBeInTheDocument();
    expect(screen.getByText('workboard.card.due')).toBeInTheDocument();
  });

  it('renders an empty list without inventing a row', () => {
    const { container } = renderWithProviders(<NeedsMeList tickets={[]} lng="fr" />);

    expect(container.querySelectorAll('li')).toHaveLength(0);
  });
});
