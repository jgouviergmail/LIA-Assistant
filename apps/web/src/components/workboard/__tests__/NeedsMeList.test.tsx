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
import { makeTicket } from '@/__tests__/factories';

function ticket(overrides: Partial<TicketRow> & { id: string }): TicketRow {
  return makeTicket({
    owner_user_id: 'me',
    title: `Ticket ${overrides.id}`,
    status: 'waiting',
    effective_assignee_id: 'me',
    ...overrides,
  });
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

    // The late ticket's badge names its due date; the other states its own.
    expect(screen.getByText('workboard.card.overdue_due')).toBeInTheDocument();
    expect(screen.queryByText('workboard.card.overdue')).not.toBeInTheDocument();
    expect(screen.getByText('workboard.card.due')).toBeInTheDocument();
  });

  it('renders an empty list without inventing a row', () => {
    const { container } = renderWithProviders(<NeedsMeList tickets={[]} lng="fr" />);

    expect(container.querySelectorAll('li')).toHaveLength(0);
  });
});

describe('the category of a ticket', () => {
  // On the board a card sits in its lane; here there is no lane to say it.
  it('shows the lane as a badge, named by the page that carries the ticket', () => {
    renderWithProviders(
      <NeedsMeList
        tickets={[ticket({ id: 'filed', category_id: 'home' })]}
        categories={{ home: 'Maison' }}
        lng="fr"
      />
    );

    expect(screen.getByTestId('category-badge')).toHaveTextContent('Maison');
    // Inside the row's own link: the badge is part of what the row says.
    expect(screen.getByRole('link', { name: /Ticket filed/ })).toContainElement(
      screen.getByTestId('category-badge')
    );
  });

  it('shows no badge for a ticket filed under nothing', () => {
    renderWithProviders(
      <NeedsMeList tickets={[ticket({ id: 'loose' })]} categories={{ home: 'Maison' }} lng="fr" />
    );

    expect(screen.queryByTestId('category-badge')).toBeNull();
  });

  it('shows no badge, and no id, for a category the page does not name', () => {
    // Deleted between two reads, or an API that predates categories.
    renderWithProviders(
      <NeedsMeList tickets={[ticket({ id: 'orphan', category_id: 'gone' })]} lng="fr" />
    );

    expect(screen.queryByTestId('category-badge')).toBeNull();
    expect(screen.queryByText(/gone/)).toBeNull();
  });
});
