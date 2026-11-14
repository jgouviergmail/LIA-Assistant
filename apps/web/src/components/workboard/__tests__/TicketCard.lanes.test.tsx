/**
 * What lanes change on a card.
 *
 * Two things, and both are easy to get wrong without anybody noticing:
 *
 * - **the card's ground is its container's opposite.** A lane on the card
 *   ground holds cards on the background, and a lane on the background holds
 *   them on the card ground — never a half tint, which is how a card ends up
 *   the colour of what it sits on (owner directive, 2026-11-08);
 * - **where nothing drags, the lane is a third list on the card** — for the
 *   OWNER only, since the category is theirs, and only once a category exists.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { makeTicket } from '@/__tests__/factories';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { TicketCard, type TicketCardProps } from '@/components/workboard/TicketCard';
import type { CategoryRow } from '@/types/workboard';

const ME = 'me-id';
const PEER = 'peer-id';

const HOME: CategoryRow = {
  id: 'home',
  owner_user_id: ME,
  name: 'Maison',
  position: 0,
  ticket_count: 1,
};
const WORK: CategoryRow = { ...HOME, id: 'work', name: 'Travail', position: 1 };

const handlers = {
  onOpen: vi.fn(),
  onFollowChange: vi.fn(),
  onDelete: vi.fn(),
  onStatusChange: vi.fn(),
  onAssigneeChange: vi.fn(),
  onCategoryChange: vi.fn(),
};

function render(overrides: Partial<TicketCardProps> = {}) {
  const ticket = makeTicket({
    id: 't1',
    owner_user_id: ME,
    title: 'Réserver la salle',
    effective_assignee_id: ME,
  });
  const props: TicketCardProps = {
    ticket,
    loaded: [ticket],
    total: 1,
    meId: ME,
    peers: [{ peer_id: PEER, peer_display_name: 'Marie' }],
    lng: 'fr',
    categories: [HOME, WORK],
    ...handlers,
    ...overrides,
  };
  return renderWithProviders(<TicketCard {...props} />);
}

beforeEach(() => vi.clearAllMocks());

describe('the ground of a card', () => {
  it('is the background by default — a column is a card-ground panel', () => {
    render();
    const card = screen.getByTestId('ticket-card');
    expect(card).toHaveClass('bg-background');
    expect(card).not.toHaveClass('bg-card');
  });

  it('is the card ground inside a lane drawn on the background', () => {
    render({ ground: 'card' });
    const card = screen.getByTestId('ticket-card');
    expect(card).toHaveClass('bg-card');
    expect(card).not.toHaveClass('bg-background');
  });

  it('is never a half tint, whatever the ground', () => {
    for (const ground of ['card', 'background'] as const) {
      const { unmount } = render({ ground });
      expect(screen.getByTestId('ticket-card').className).not.toMatch(/bg-(card|background)\/\d/);
      unmount();
    }
  });
});

describe('the lane as a list on the card, where nothing drags', () => {
  const laneList = () => screen.queryByRole('combobox', { name: 'workboard.card.category_of' });

  it('is offered to the owner once a category exists', () => {
    render();
    expect(laneList()).toBeInTheDocument();
  });

  it('is not drawn while the account has no category', () => {
    render({ categories: [] });
    expect(laneList()).not.toBeInTheDocument();
  });

  it('is not drawn for a holder: the category is the owner’s', () => {
    render({
      ticket: makeTicket({ id: 't1', owner_user_id: PEER, effective_assignee_id: ME }),
    });
    expect(laneList()).not.toBeInTheDocument();
  });

  it('is not drawn where the card drags: the lane is then the drag itself', () => {
    render({ dragHandle: { role: 'button' } });
    expect(laneList()).not.toBeInTheDocument();
  });

  it('is not drawn on a surface that cannot act', () => {
    render({ onCategoryChange: undefined });
    expect(laneList()).not.toBeInTheDocument();
  });
});
