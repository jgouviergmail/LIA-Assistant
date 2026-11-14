/**
 * The board, once its reader has categories: one lane per category.
 *
 * Reached through `Board`, the way the page reaches it — the choice between
 * the flat board and the lane board is part of what is under test.
 *
 * What these tests hold: a card sits in the cell of ITS lane and ITS column;
 * the lanes are told apart by a ground that alternates, the cards on the
 * opposite one; a lane's figures are the server's, and a cell that holds more
 * than the page carries says so; an empty lane costs one line; and the
 * category being the OWNER's, a lane the card in the air may not enter is
 * visibly closed. The drop arithmetic is proven on the pure functions
 * (`lane-dnd.test.ts`) and the gesture itself in a browser.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { makeTicket } from '@/__tests__/factories';
import { act, fireEvent, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { Board, type BoardProps } from '@/components/workboard/Board';
import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';
import type { CategoryRow, LaneRow, TicketRow } from '@/types/workboard';

const wide = vi.hoisted(() => ({ value: true }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => wide.value }));

// The suite's `t` echoes the key and drops the values. A lane is told apart by
// its NAME and its count, so this file keeps them — one stable function, as
// the real hook memoises it.
const i18n = vi.hoisted(() => ({
  t: (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
  i18n: { language: 'fr' },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => i18n }));

const ME = 'me';
const PEER = 'peer';

function ticket(
  id: string,
  status: string,
  position: number,
  category_id: string | null,
  owner_user_id: string = ME
): TicketRow {
  return makeTicket({
    id,
    title: `Ticket ${id}`,
    status,
    position,
    category_id,
    owner_user_id,
    effective_assignee_id: ME,
  });
}

/** `todo`, in column order: u1, h1, s1, h2. `done`: h3. */
const ROWS: TicketRow[] = [
  ticket('u1', 'todo', 0, null),
  ticket('h1', 'todo', 1, 'home'),
  ticket('s1', 'todo', 2, 'shared', PEER),
  ticket('h2', 'todo', 3, 'home'),
  ticket('h3', 'done', 0, 'home'),
];

function lane(
  category_id: string | null,
  name: string | null,
  counts: Record<string, number>,
  owner_user_id: string | null = category_id === null ? null : ME
): LaneRow {
  return {
    category_id,
    name,
    owner_user_id,
    counts_by_status: {
      idea: 0,
      todo: 0,
      in_progress: 0,
      waiting: 0,
      validating: 0,
      done: 0,
      ...counts,
    },
  };
}

const LANES: LaneRow[] = [
  lane(null, null, { todo: 1 }),
  lane('home', 'Maison', { todo: 2, done: 1 }),
  lane('work', 'Travail', {}),
  lane('shared', 'Chantier', { todo: 1 }, PEER),
];

const CATEGORIES: CategoryRow[] = [
  { id: 'home', owner_user_id: ME, name: 'Maison', position: 0, ticket_count: 3 },
  { id: 'work', owner_user_id: ME, name: 'Travail', position: 1, ticket_count: 0 },
];

const handlers = {
  onOpen: vi.fn(),
  onMove: vi.fn(),
  onFollowChange: vi.fn(),
  onDelete: vi.fn(),
  onAdd: vi.fn(),
};

function render(overrides: Partial<BoardProps> = {}) {
  const props: BoardProps = {
    column: (status: string) => ROWS.filter(row => row.status === status),
    countsByStatus: { idea: 0, todo: 4, in_progress: 0, waiting: 0, validating: 0, done: 1 },
    loaded: ROWS,
    total: 5,
    meId: ME,
    peers: [{ peer_id: PEER, peer_display_name: 'Marie' }],
    lng: 'fr',
    lanes: LANES,
    ...handlers,
    ...overrides,
  };
  return renderWithProviders(<Board {...props} />);
}

/**
 * dnd-kit's keyboard sensor starts listening for the NEXT key one task after
 * the key that picked the card up — a key sent sooner is not heard.
 */
const nextTask = () =>
  act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });

const cardsIn = (testId: string) =>
  within(screen.getByTestId(testId))
    .queryAllByTestId('ticket-card')
    .map(card => card.textContent ?? '');

beforeEach(() => {
  vi.clearAllMocks();
  wide.value = true;
  useWorkboardLanesStore.setState({ collapsed: [] });
});

describe('the choice between the two boards', () => {
  it('keeps the flat board for a reader with no category in sight', () => {
    render({ lanes: [] });

    expect(screen.queryByTestId('lane-unfiled')).toBeNull();
    expect(screen.getAllByRole('region')).toHaveLength(6);
  });
});

describe('from lg up', () => {
  it('draws one lane per category in the server’s order, the unfiled one first', () => {
    render();

    expect(screen.getAllByRole('region').map(region => region.getAttribute('data-testid'))).toEqual(
      ['lane-unfiled', 'lane-home', 'lane-work', 'lane-shared']
    );
    expect(
      screen.getByRole('region', { name: 'workboard.lanes.label {"name":"Maison"}' })
    ).toBeInTheDocument();
    // The unfiled lane has no name of its own: the locale names it.
    expect(
      screen.getByRole('region', {
        name: 'workboard.lanes.label {"name":"workboard.lanes.unfiled"}',
      })
    ).toBeInTheDocument();
  });

  it('puts each card in the cell of its lane and its column', () => {
    render();

    expect(cardsIn('cell-unfiled-todo')).toHaveLength(1);
    expect(cardsIn('cell-home-todo')).toHaveLength(2);
    expect(cardsIn('cell-home-done')).toHaveLength(1);
    expect(cardsIn('cell-shared-todo')).toHaveLength(1);
    expect(cardsIn('cell-home-idea')).toHaveLength(0);
    expect(screen.getAllByTestId('ticket-card')).toHaveLength(ROWS.length);
  });

  it('names the columns ONCE, above the lanes, with the column’s exact count', () => {
    render();

    const headers = screen.getAllByTestId(/^column-header-/);
    expect(headers).toHaveLength(6);
    expect(screen.getByTestId('count-todo')).toHaveTextContent(
      'workboard.board.column_count {"count":4}'
    );
  });

  it('marks the columns with a thin rule between them, under their names and in every lane', () => {
    // Owner, 2026-11-11: with six columns across and a ground per lane, nothing
    // said where one column ended. ONE rule per boundary: none before the
    // first column, and the names' row is ruled where the cells are.
    render();

    const ruled = (nodes: Element[]) =>
      nodes.map(node => !!node.querySelector('[data-column-rule]'));
    const names = screen.getAllByTestId(/^column-header-/);
    expect(names.length).toBeGreaterThan(1);
    expect(ruled(names)).toEqual([false, ...names.slice(1).map(() => true)]);

    const cells = within(screen.getByTestId('lane-home')).getAllByTestId(/^cell-home-/);
    expect(cells).toHaveLength(names.length);
    expect(ruled(cells)).toEqual([false, ...cells.slice(1).map(() => true)]);
    // Decoration: a rule is nothing a screen reader should meet.
    for (const rule of document.querySelectorAll('[data-column-rule]')) {
      expect(rule).toHaveAttribute('aria-hidden', 'true');
    }
  });

  it('alternates the grounds from one lane to the next, the cards on the opposite one', () => {
    render();

    const grounds = ['lane-unfiled', 'lane-home', 'lane-work', 'lane-shared'].map(id =>
      screen.getByTestId(id).getAttribute('data-lane-ground')
    );
    expect(grounds).toEqual(['card', 'background', 'card', 'background']);
    expect(screen.getByTestId('lane-unfiled')).toHaveClass('bg-card');
    expect(screen.getByTestId('lane-home')).toHaveClass('bg-background');
    // Never a card the colour of what it sits on.
    const [unfiled] = within(screen.getByTestId('cell-unfiled-todo')).getAllByTestId('ticket-card');
    expect(unfiled).toHaveClass('bg-background');
    const [home] = within(screen.getByTestId('cell-home-todo')).getAllByTestId('ticket-card');
    expect(home).toHaveClass('bg-card');
  });

  it('counts a lane from the server and says what this page does not carry', () => {
    // The lane holds 5 « to do »; the page carries 2 of them.
    render({
      lanes: [LANES[0], lane('home', 'Maison', { todo: 5, done: 1 }), LANES[2], LANES[3]],
    });

    expect(screen.getByTestId('lane-count-home')).toHaveTextContent(
      'workboard.board.column_count {"count":6}'
    );
    expect(
      within(screen.getByTestId('cell-home-todo')).getByText('workboard.lanes.off_page {"count":3}')
    ).toBeInTheDocument();
    expect(within(screen.getByTestId('cell-home-done')).queryByText(/off_page/)).toBeNull();
  });

  it('draws an empty lane as its header alone, with nothing to fold', () => {
    render();

    const empty = screen.getByTestId('lane-work');
    expect(within(empty).queryByTestId(/^cell-/)).toBeNull();
    expect(within(empty).queryByRole('button', { name: /workboard\.lanes\.collapse/ })).toBeNull();
    expect(screen.getByTestId('lane-count-work')).toHaveTextContent('{"count":0}');
  });

  it('does not draw a lane a filter emptied', () => {
    render({ narrowed: true });

    expect(screen.queryByTestId('lane-work')).toBeNull();
    expect(screen.getByTestId('lane-home')).toBeInTheDocument();
  });

  it('says whose lane somebody else’s is, and offers no ticket in it', () => {
    render();

    const theirs = screen.getByTestId('lane-shared');
    // In the lane's HEADER: the card under it says the same of its ticket.
    const header = theirs.querySelector('header');
    expect(header).toHaveTextContent('workboard.party.owned_by {"name":"Marie"}');
    expect(
      within(theirs).queryByRole('button', { name: /workboard\.lanes\.add_ticket/ })
    ).toBeNull();
    // The reader's own lanes say nothing of the kind.
    expect(screen.getByTestId('lane-home').querySelector('header')).not.toHaveTextContent(
      /owned_by/
    );
  });

  it('creates a ticket straight into a lane of the reader’s', async () => {
    const { user } = render();

    await user.click(
      screen.getByRole('button', { name: 'workboard.lanes.add_ticket {"name":"Maison"}' })
    );
    expect(handlers.onAdd).toHaveBeenLastCalledWith('home');

    await user.click(
      screen.getByRole('button', {
        name: 'workboard.lanes.add_ticket {"name":"workboard.lanes.unfiled"}',
      })
    );
    expect(handlers.onAdd).toHaveBeenLastCalledWith(null);
  });

  it('folds a lane to its header, says so, and remembers it on the device', async () => {
    const { user } = render();

    const fold = screen.getByRole('button', {
      name: 'workboard.lanes.collapse {"name":"Maison"}',
    });
    expect(fold).toHaveAttribute('aria-expanded', 'true');
    await user.click(fold);

    expect(screen.queryByTestId('cell-home-todo')).toBeNull();
    const unfold = screen.getByRole('button', { name: 'workboard.lanes.expand {"name":"Maison"}' });
    expect(unfold).toHaveAttribute('aria-expanded', 'false');
    // The fold button is the one the click landed on: it must still hold focus.
    expect(unfold).toHaveFocus();
    expect(useWorkboardLanesStore.getState().collapsed).toEqual(['home']);
    // The other lanes are untouched.
    expect(cardsIn('cell-unfiled-todo')).toHaveLength(1);

    await user.click(unfold);
    expect(cardsIn('cell-home-todo')).toHaveLength(2);
    expect(useWorkboardLanesStore.getState().collapsed).toEqual([]);
  });

  it('keeps the fold of a lane a filter is hiding', async () => {
    // « Travail » is folded and empty under the filter, so it is not drawn.
    // Folding another lane must not forget it: the filter will be lifted.
    useWorkboardLanesStore.setState({ collapsed: ['work'] });
    const { user } = render({ narrowed: true });

    await user.click(
      screen.getByRole('button', { name: 'workboard.lanes.collapse {"name":"Maison"}' })
    );

    expect(useWorkboardLanesStore.getState().collapsed).toEqual(['work', 'home']);
  });

  it('makes every card a thing that can be picked up', () => {
    render();

    for (const card of screen.getAllByTestId('ticket-card')) {
      expect(card).toHaveAttribute('aria-roledescription');
    }
    // The lists are the phone's: here the lane and the column are the drag.
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('closes, visibly, the lanes the card in the air may not enter', async () => {
    render();
    const closedLanes = () =>
      screen
        .getAllByRole('region')
        .filter(region => region.classList.contains('opacity-50'))
        .map(region => region.getAttribute('data-testid'));
    expect(closedLanes()).toEqual([]);

    // The reader's own ticket: every lane of theirs, never somebody else's.
    const [mine] = within(screen.getByTestId('cell-home-todo')).getAllByTestId('ticket-card');
    fireEvent.keyDown(mine, { code: 'Space' });
    expect(closedLanes()).toEqual(['lane-shared']);
    await nextTask();
    fireEvent.keyDown(mine, { code: 'Escape' });
    expect(closedLanes()).toEqual([]);

    // A ticket the reader only HOLDS stays in its owner's lane.
    const [held] = within(screen.getByTestId('cell-shared-todo')).getAllByTestId('ticket-card');
    fireEvent.keyDown(held, { code: 'Space' });
    expect(closedLanes()).toEqual(['lane-unfiled', 'lane-home', 'lane-work']);
  });

  it('tells the page while a card is in the air', async () => {
    const onDragActive = vi.fn();
    render({ onDragActive });

    const [card] = screen.getAllByTestId('ticket-card');
    fireEvent.keyDown(card, { code: 'Space' });
    expect(onDragActive).toHaveBeenLastCalledWith(true);
    await nextTask();
    fireEvent.keyDown(card, { code: 'Escape' });
    expect(onDragActive).toHaveBeenLastCalledWith(false);
    expect(handlers.onMove).not.toHaveBeenCalled();
  });
});

describe('below lg', () => {
  beforeEach(() => {
    wide.value = false;
  });

  it('rules nothing: ONE column has no boundary to mark', () => {
    render();

    expect(document.querySelector('[data-column-rule]')).toBeNull();
  });

  it('shows ONE column, grouped by lane', () => {
    render();

    expect(
      screen.getByRole('combobox', { name: 'workboard.board.pick_column' })
    ).toBeInTheDocument();
    expect(cardsIn('cell-home-todo')).toHaveLength(2);
    expect(screen.queryByTestId('cell-home-done')).toBeNull();
    // The column is named by the picker: no second row of headers.
    expect(screen.queryByTestId(/^column-header-/)).toBeNull();
  });

  it('counts each lane for the column on screen, and walks the columns', async () => {
    const { user } = render();

    expect(screen.getByTestId('lane-count-home')).toHaveTextContent('{"count":2}');
    // A lane with nothing in THIS column is its header alone.
    expect(within(screen.getByTestId('lane-work')).queryByTestId(/^cell-/)).toBeNull();

    await user.click(screen.getByRole('button', { name: 'workboard.board.previous_column' }));
    expect(screen.getByTestId('lane-count-home')).toHaveTextContent('{"count":0}');
    expect(screen.queryByTestId('cell-home-todo')).toBeNull();
  });

  it('never picks a card up: the lane is a list on the owner’s cards', () => {
    const onCategoryChange = vi.fn();
    render({
      categories: CATEGORIES,
      onCategoryChange,
      onStatusChange: vi.fn(),
      onAssigneeChange: vi.fn(),
    });

    for (const card of screen.getAllByTestId('ticket-card')) {
      expect(card).not.toHaveAttribute('aria-roledescription');
    }
    // Three of the reader's own tickets sit in « to do »; the fourth is held
    // for somebody else, whose category it is.
    expect(screen.getAllByRole('combobox', { name: /workboard\.card\.category_of/ })).toHaveLength(
      3
    );
  });

  it('pins each lane’s name under the application header while its cards scroll', () => {
    render();

    const header = screen.getByTestId('lane-home').querySelector('header');
    expect(header).toHaveClass('sticky', 'top-16');
    // On the lane's own ground, so the cards pass beneath it.
    expect(header).toHaveClass('bg-background');
  });
});
