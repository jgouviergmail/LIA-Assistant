/**
 * The board at two widths.
 *
 * From `lg` up: seven columns, drag AND keyboard, exact counters. Below it: one
 * column at a time and NO drag — a finger scrolling a list must never pick a
 * card up, and dragging across seven columns on a 390 px screen is not a
 * gesture anybody wants. Both widths write the move through the SAME mutation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { fireEvent, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { Board, type BoardProps } from '@/components/workboard/Board';
import type { TicketRow } from '@/types/workboard';

const wide = vi.hoisted(() => ({ value: true }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => wide.value }));

function ticket(id: string, status: string, position = 0): TicketRow {
  return {
    id,
    owner_user_id: 'me',
    parent_id: null,
    title: `Ticket ${id}`,
    description: null,
    status,
    priority: 'medium',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: 'me',
    position,
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
  };
}

const ROWS: Record<string, TicketRow[]> = {
  todo: [ticket('a', 'todo', 0), ticket('b', 'todo', 1)],
  done: [ticket('z', 'done', 0)],
};

const handlers = {
  onOpen: vi.fn(),
  onMove: vi.fn(),
  onFollowChange: vi.fn(),
  onDelete: vi.fn(),
};

function render(overrides: Partial<BoardProps> = {}) {
  return renderWithProviders(boardElement(overrides));
}

/**
 * The board with the harness defaults.
 *
 * An ELEMENT rather than a render, so a test can hand the same tree back to
 * `rerender` — which is how a column that empties under the reader is
 * observed, and the only way to see it without remounting the component and
 * resetting the very state under test.
 */
function boardElement(overrides: Partial<BoardProps> = {}) {
  const props: BoardProps = {
    column: (status: string) => ROWS[status] ?? [],
    // The server's aggregate: `todo` holds 87, of which this page carries 2.
    countsByStatus: {
      idea: 0,
      todo: 87,
      in_progress: 0,
      waiting: 0,
      validating: 0,
      done: 1,
    },
    loaded: [...ROWS.todo, ...ROWS.done],
    total: 88,
    meId: 'me',
    peers: [],
    lng: 'fr',
    ...handlers,
    ...overrides,
  };
  return <Board {...props} />;
}

beforeEach(() => {
  vi.clearAllMocks();
  wide.value = true;
});

describe('from lg up', () => {
  it('carries no list on the cards: the column is the drag', () => {
    render({ onStatusChange: vi.fn(), onAssigneeChange: vi.fn() });

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('shows the six columns inside ONE horizontal scroller', () => {
    const { container } = render();

    expect(screen.getAllByRole('region')).toHaveLength(6);
    // The page body must never scroll sideways: the columns do.
    expect(container.querySelector('.overflow-x-auto')).not.toBeNull();
  });

  it('counts a column from the SERVER aggregate, never from the page', () => {
    // Two cards are on screen; the column holds 87. Deriving the header from
    // `tickets.length` would under-report every column past the first page.
    render();

    expect(screen.getByTestId('count-todo')).toHaveTextContent('workboard.board.column_count');
    expect(within(screen.getByTestId('column-todo')).getAllByTestId('ticket-card')).toHaveLength(2);
  });

  it('names every column for a screen reader', () => {
    render();

    expect(screen.getByRole('region', { name: 'workboard.columns.todo' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'workboard.columns.done' })).toBeInTheDocument();
  });

  it('says a column is empty rather than showing an empty box', () => {
    render();

    expect(screen.getAllByText('workboard.empty.column').length).toBeGreaterThan(0);
  });

  it('never says « nothing here » under a count that says otherwise', () => {
    // The page is capped at 200 rows and an account may own 2 000, so a
    // column whose tickets all sit past the page is REAL — and « Rien ici »
    // under a header saying 87 is exactly the disagreement ADR-185 forbids.
    render({
      column: () => [],
      countsByStatus: {
        idea: 0,
        todo: 87,
        in_progress: 0,
        waiting: 0,
        validating: 0,
        done: 0,
      },
    });

    const todo = screen.getByRole('region', { name: 'workboard.columns.todo' });
    expect(within(todo).queryByText('workboard.empty.column')).toBeNull();
    expect(within(todo).getByText('workboard.empty.column_off_page')).toBeInTheDocument();
    // A genuinely empty column still says so.
    const done = screen.getByRole('region', { name: 'workboard.columns.done' });
    expect(within(done).getByText('workboard.empty.column')).toBeInTheDocument();
  });
});

describe('below lg', () => {
  beforeEach(() => {
    wide.value = false;
  });

  it('shows ONE column, chosen with the column list carrying its count', async () => {
    const { user } = render();

    expect(screen.getAllByRole('region')).toHaveLength(1);
    const picker = screen.getByRole('combobox', { name: 'workboard.board.pick_column' });
    // The count travels with the name, so choosing a column is an informed pick.
    expect(picker).toHaveTextContent('workboard.columns.todo (87)');
    await user.click(picker);
    expect(await screen.findAllByRole('option')).toHaveLength(6);
    expect(screen.getByRole('option', { name: 'workboard.columns.todo (87)' })).toBeInTheDocument();
    // The SAME list a card carries: each item wears its column's glyph (lot 20).
    expect(
      screen
        .getByRole('option', { name: /workboard.columns.done/ })
        .querySelector('.lucide-circle-check')
    ).not.toBeNull();
  });

  it('walks the columns with the two arrows, and stops at both ends', async () => {
    const { user } = render();

    // `todo` is the second column: previous is available, and lands on `idea`.
    await user.click(screen.getByRole('button', { name: 'workboard.board.previous_column' }));
    expect(screen.getByRole('region', { name: 'workboard.columns.idea' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'workboard.board.previous_column' })).toBeDisabled();
  });

  it('never picks a card up on the narrow layout: a press is a tap that opens it', () => {
    // Nothing drags on a phone (owner, 2026-09-10): the panel is where the
    // column and the holder change, and a finger on a card opens it.
    render();

    const card = screen.getAllByTestId('ticket-card')[0];
    expect(card.className).not.toContain('cursor-grab');
    expect(card).not.toHaveAttribute('aria-roledescription');
  });

  it('carries the column and the holder as lists on every card, since nothing drags', () => {
    render({ onStatusChange: vi.fn(), onAssigneeChange: vi.fn() });

    expect(screen.getAllByRole('combobox', { name: /workboard\.card\.column_of/ })).toHaveLength(2);
    expect(screen.getAllByRole('combobox', { name: /workboard\.card\.holder_of/ })).toHaveLength(2);
  });

  it('keeps a gesture started inside an open list to the list, never to the board', async () => {
    // The list is portalled but the React tree runs through the portal: a
    // swipe across an item would otherwise reach the column swipe underneath
    // and turn a pick into a page turn.
    const { user } = render({ onStatusChange: vi.fn(), onAssigneeChange: vi.fn() });

    await user.click(screen.getAllByRole('combobox', { name: /workboard\.card\.column_of/ })[0]);
    const option = await screen.findByRole('option', { name: 'workboard.columns.done' });
    fireEvent.touchStart(option, { touches: [{ clientX: 300, clientY: 200 }] });
    fireEvent.touchEnd(option, { changedTouches: [{ clientX: 100, clientY: 200 }] });

    // Read back once the list is closed: while it is open, Radix hides the
    // rest of the page from the accessibility tree, region included.
    await user.keyboard('{Escape}');
    expect(screen.getByRole('region', { name: 'workboard.columns.todo' })).toBeInTheDocument();
  });

  const swipe = (from: number, to: number, dy = 0) => {
    const surface = screen.getByRole('region').parentElement as HTMLElement;
    fireEvent.touchStart(surface, { touches: [{ clientX: from, clientY: 200 }] });
    fireEvent.touchEnd(surface, { changedTouches: [{ clientX: to, clientY: 200 + dy }] });
  };

  it('a swipe to the left shows the next column, a swipe to the right the previous', () => {
    render();

    swipe(300, 200);
    expect(
      screen.getByRole('region', { name: 'workboard.columns.in_progress' })
    ).toBeInTheDocument();

    swipe(100, 220);
    expect(screen.getByRole('region', { name: 'workboard.columns.todo' })).toBeInTheDocument();
  });

  it('a short or a mostly vertical travel is a scroll, never a swipe', () => {
    render();

    swipe(300, 270);
    swipe(300, 200, 90);

    expect(screen.getByRole('region', { name: 'workboard.columns.todo' })).toBeInTheDocument();
  });

  it('stops at the last column instead of wrapping', () => {
    render();

    for (let i = 0; i < 8; i += 1) swipe(300, 100);

    expect(screen.getByRole('region', { name: 'workboard.columns.done' })).toBeInTheDocument();
  });
});

describe('the « to confirm » column', () => {
  // Lot 7: drawn only while it holds a ticket — an empty eighth column on
  // every board would be the price of a feature most boards never use.
  it('is absent while nothing waits for a confirmation', () => {
    render();

    expect(screen.getAllByRole('region')).toHaveLength(6);
    expect(screen.queryByRole('region', { name: 'workboard.columns.confirming' })).toBeNull();
  });

  it('is absent when the server does not even count it', () => {
    // An older API answers without the key at all; `?? 0` reads that as empty.
    const { idea, todo, in_progress, waiting, validating, done } = {
      idea: 0,
      todo: 1,
      in_progress: 0,
      waiting: 0,
      validating: 0,
      done: 0,
    };
    render({ countsByStatus: { idea, todo, in_progress, waiting, validating, done } });

    expect(screen.queryByRole('region', { name: 'workboard.columns.confirming' })).toBeNull();
  });

  it('appears, in its place, as soon as one ticket waits', () => {
    render({
      column: (status: string) =>
        status === 'confirming' ? [ticket('c', 'confirming', 0)] : (ROWS[status] ?? []),
      countsByStatus: {
        idea: 0,
        todo: 87,
        in_progress: 0,
        waiting: 0,
        confirming: 1,
        validating: 0,
        done: 1,
      },
    });

    const names = screen.getAllByRole('region').map(region => region.getAttribute('aria-label'));
    expect(names).toHaveLength(7);
    expect(names.indexOf('workboard.columns.confirming')).toBe(
      names.indexOf('workboard.columns.waiting') + 1
    );
    expect(
      within(screen.getByTestId('column-confirming')).getAllByTestId('ticket-card')
    ).toHaveLength(1);
  });

  it('is offered by the phone picker only then', async () => {
    wide.value = false;
    const { user } = render();
    await user.click(screen.getByRole('combobox', { name: 'workboard.board.pick_column' }));
    await screen.findAllByRole('option');
    expect(screen.queryByRole('option', { name: /workboard.columns.confirming/ })).toBeNull();
  });

  it('does not strand the phone on a column that has just emptied', async () => {
    // The one column that comes and goes. A person watching « À confirmer »
    // answers the ticket, the column stops being drawn — and the phone was
    // left showing a column no list offered any more: the picker had no
    // selected value and the « previous » arrow was dead.
    wide.value = false;
    const holding = {
      idea: 0,
      todo: 87,
      in_progress: 0,
      waiting: 0,
      confirming: 1,
      validating: 0,
      done: 1,
    };
    const holdingProps: Partial<BoardProps> = {
      column: (status: string) =>
        status === 'confirming' ? [ticket('c', 'confirming', 0)] : (ROWS[status] ?? []),
      countsByStatus: holding,
    };
    const { user, rerender } = render(holdingProps);

    await user.click(screen.getByRole('combobox', { name: 'workboard.board.pick_column' }));
    await user.click(await screen.findByRole('option', { name: /workboard.columns.confirming/ }));
    expect(screen.getByRole('region', { name: 'workboard.columns.confirming' })).toBeInTheDocument();

    // The ticket is answered: the server stops counting the column, and the
    // board stops drawing it under the reader.
    rerender(
      boardElement({ ...holdingProps, countsByStatus: { ...holding, confirming: 0 } })
    );

    // Exactly one column is shown, and it is one the board still draws.
    const regions = screen.getAllByRole('region');
    expect(regions).toHaveLength(1);
    expect(regions[0].getAttribute('aria-label')).not.toBe('workboard.columns.confirming');
    // And the list agrees with what is on screen.
    expect(
      screen.getByRole('combobox', { name: 'workboard.board.pick_column' })
    ).toHaveTextContent(String(regions[0].getAttribute('aria-label')));
  });
});

describe('a column that holds something is alive', () => {
  // Motion is the SIGNAL, so an empty column is still. Both animations are
  // `motion-safe`, so a reader who asked for stillness keeps it.
  it('breathes on a column that holds tickets', () => {
    render();

    const header = screen.getByRole('region', { name: 'workboard.columns.todo' });
    expect(header.querySelector('.motion-safe\\:animate-pulse')).not.toBeNull();
  });

  it('stays still on an empty one', () => {
    render();

    const header = screen.getByRole('region', { name: 'workboard.columns.idea' });
    expect(header.querySelector('[class*="motion-safe"]')).toBeNull();
  });

  it('spins « en cours », whose glyph IS a spinner', () => {
    render({
      column: (status: string) =>
        status === 'in_progress' ? [ticket('c', 'in_progress', 0)] : (ROWS[status] ?? []),
      countsByStatus: {
        idea: 0,
        todo: 87,
        in_progress: 1,
        waiting: 0,
        validating: 0,
        done: 1,
      },
    });

    const header = screen.getByRole('region', { name: 'workboard.columns.in_progress' });
    expect(header.querySelector('.motion-safe\\:animate-spin')).not.toBeNull();
  });
});
