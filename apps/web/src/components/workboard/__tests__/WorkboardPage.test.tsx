/**
 * The board screen: what it shows before the data, when there is none, and
 * when the instance switched the feature off.
 *
 * The two empty states are deliberately different: « nothing yet » invites a
 * first ticket, « no match » says the board is not empty — these filters are.
 * Confusing them sends a person looking for work that is right there.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  act,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import { handOff, setHandoffOwner } from '@/lib/workbench/handoff';
import { WorkboardPage } from '@/components/workboard/WorkboardPage';
import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';
import type {
  BoardFilters,
  BoardSummary,
  CategoryRow,
  LaneRow,
  TicketRow,
} from '@/types/workboard';
import { makeTicket } from '@/__tests__/factories';
import { hasFilters } from '@/lib/workboard/active-filters';

const board = vi.hoisted(() => ({
  tickets: [] as TicketRow[],
  countsByStatus: {} as Record<string, number>,
  lanes: [] as LaneRow[],
  total: 0,
  column: (_status: string) => [] as TicketRow[],
  firstLoad: false,
  loading: false,
  error: null as Error | null,
  isUnavailable: false,
  refetch: vi.fn(),
  move: vi.fn(),
  patch: vi.fn(),
  create: vi.fn(),
  comment: vi.fn(),
  runNow: vi.fn(),
  remove: vi.fn(),
}));
const readBoard = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useWorkboard', () => ({
  useWorkboard: (filters: BoardFilters) => {
    readBoard(filters);
    return board;
  },
}));
// The manager's own read: asked for only while the dialog is open.
const categories = vi.hoisted(() => ({
  own: [] as CategoryRow[],
  maxCategories: 20 as number | undefined,
  nameMaxChars: 40 as number | undefined,
  firstLoad: false,
  error: false,
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}));
const readCategories = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useWorkboardCategories', () => ({
  useWorkboardCategories: (enabled: boolean) => {
    readCategories(enabled);
    return categories;
  },
}));
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipients: () => [] }));
const { account, notices } = vi.hoisted(() => ({
  account: { id: 'me' },
  notices: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account }) }));
vi.mock('sonner', () => ({ toast: notices }));
// The screen's size: a phone folds the filters and the board's figures.
const viewport = vi.hoisted(() => ({ wide: true }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => viewport.wide }));
// The board's figures: read only while their block is open and the board known.
const figures = vi.hoisted(() => ({
  summary: undefined as BoardSummary | undefined,
  reads: [] as Array<[boolean, string]>,
}));
vi.mock('@/hooks/useWorkboardSummary', () => ({
  useWorkboardSummary: (enabled: boolean, stamp: string) => {
    figures.reads.push([enabled, stamp]);
    return { summary: enabled ? figures.summary : undefined, loading: false, error: false };
  },
}));

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
}));

function render(initialTicketId?: string) {
  return renderWithProviders(<WorkboardPage lng="fr" initialTicketId={initialTicketId} />);
}

beforeEach(() => {
  account.id = 'me';
  vi.clearAllMocks();
  Object.assign(board, {
    tickets: [],
    countsByStatus: {},
    lanes: [],
    total: 0,
    column: () => [],
    firstLoad: false,
    loading: false,
    error: null,
    isUnavailable: false,
  });
  categories.own = [];
  viewport.wide = true;
  figures.summary = undefined;
  figures.reads = [];
  window.localStorage.clear();
  useWorkboardLanesStore.setState({ collapsed: [], summaryOpen: null });
});
afterEach(() => setHandoffOwner(null));

it('retires a proposed form and its late completion on account change', async () => {
  setHandoffOwner('me');
  let finish: (value: { ok: boolean; errorCode: null }) => void = () => undefined;
  board.create.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      })
  );
  const view = render();
  act(() => {
    handOff('me', { kind: 'ticket', ticket: { title: 'Private ticket', description: '' } });
  });
  await screen.findByRole('dialog');
  await view.user.click(
    screen.getAllByRole('button', { name: 'workboard.actions.create' }).at(-1)!
  );
  act(() => {
    account.id = 'another';
    setHandoffOwner('another');
  });
  view.rerender(<WorkboardPage lng="fr" />);
  await act(async () => finish({ ok: true, errorCode: null }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(notices.success).not.toHaveBeenCalled();
  expect(notices.error).not.toHaveBeenCalled();
});

it('opens a reviewable native ticket and writes only after explicit creation', async () => {
  setHandoffOwner('me');
  board.create.mockResolvedValue({ ok: true, errorCode: null });
  const { user } = render();
  act(() => {
    handOff('me', {
      kind: 'ticket',
      ticket: { title: 'Call Ana', description: 'Ask about the quote' },
    });
  });
  expect(await screen.findByRole('dialog')).toBeVisible();
  expect(screen.getByLabelText('workboard.form.title')).toHaveValue('Call Ana');
  expect(screen.getByLabelText('workboard.form.description')).toHaveValue('Ask about the quote');
  expect(board.create).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'workboard.actions.create' }));
  expect(board.create).toHaveBeenCalledWith(
    expect.objectContaining({
      title: 'Call Ana',
      description: 'Ask about the quote',
      assignee: 'me',
    })
  );
});

it('waits for the existing ticket form to close before receiving another proposal', async () => {
  setHandoffOwner('me');
  const { user } = render();
  await user.click(screen.getAllByRole('button', { name: 'workboard.actions.create' })[0]);
  await user.type(screen.getByLabelText('workboard.form.title'), 'My unfinished ticket');
  act(() => {
    handOff('me', { kind: 'ticket', ticket: { title: 'New proposal', description: '' } });
  });
  expect(screen.getByLabelText('workboard.form.title')).toHaveValue('My unfinished ticket');
  expect(notices.info).toHaveBeenCalledOnce();
  await user.click(screen.getByRole('button', { name: 'workboard.actions.cancel' }));
  expect(await screen.findByLabelText('workboard.form.title')).toHaveValue('New proposal');
  expect(board.create).not.toHaveBeenCalled();
});

describe('before anything has been read', () => {
  it('keeps a dashboard card filter in the embedded reader without rewriting the host URL', () => {
    const filters: BoardFilters = {
      assignee: 'lia',
      sort: 'due',
      overdue: true,
      q: 'Selected ticket',
      status: ['todo'],
    };
    renderWithProviders(<WorkboardPage lng="fr" embedded initialFilters={filters} />);
    expect(screen.getByLabelText('workboard.filters.search')).toHaveValue('Selected ticket');
    expect(readBoard).toHaveBeenLastCalledWith(filters);
    expect(router.replace).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });
  it('shows a skeleton of the real geometry and announces the load', () => {
    board.firstLoad = true;
    const { container } = render();

    expect(
      container.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length
    ).toBeGreaterThan(0);
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();
  });
});

describe('when the board is empty', () => {
  it('invites a first ticket, and says so as « nothing yet »', () => {
    render();

    const empty = screen.getByTestId('empty-state');
    expect(empty).toHaveAttribute('data-reason', 'no-data');
    expect(screen.getByText('workboard.empty.title')).toBeInTheDocument();
  });

  it('says « no match » instead once the reader narrowed the board', async () => {
    // The board is not empty — these filters are. Telling a person their board
    // is empty while a filter hides everything sends them looking for work
    // that is right there.
    const { user } = render();
    await user.type(screen.getByLabelText('workboard.filters.search'), 'zzz');

    const empty = screen.getByTestId('empty-state');
    expect(empty).toHaveAttribute('data-reason', 'no-match');
    expect(screen.getByText('workboard.empty.filtered_title')).toBeInTheDocument();
  });
});

describe('when the instance switched the workboard off', () => {
  it('says so instead of showing an error', () => {
    // The router is absent, so the API answers 404 — a configuration answer,
    // not a failure to report.
    board.isUnavailable = true;
    render();

    expect(screen.getByText('workboard.unavailable')).toBeInTheDocument();
    expect(screen.queryByText('workboard.load_error')).not.toBeInTheDocument();
  });
});

describe('when the board could not be read', () => {
  it('says the read failed, and does not claim the board is empty', () => {
    board.error = new Error('boom');
    render();

    expect(screen.getByText('workboard.load_error')).toBeInTheDocument();
    expect(screen.queryByText('workboard.empty.title')).not.toBeInTheDocument();
  });
});

describe('the exact total', () => {
  it('comes from the server, not from the page', () => {
    const row: TicketRow = makeTicket({
      id: 'a',
      owner_user_id: 'me',
      title: 'A',
      effective_assignee_id: 'me',
    });
    Object.assign(board, {
      tickets: [row],
      total: 87,
      countsByStatus: { todo: 87 },
      column: (status: string) => (status === 'todo' ? [row] : []),
    });
    render();

    expect(screen.getByText('workboard.filters.total')).toBeInTheDocument();
    expect(screen.getAllByTestId('ticket-card')).toHaveLength(1);
  });
});

describe('the board at a glance', () => {
  const glance = () => screen.getByText('workboard.summary.title').closest('details');
  const whole: BoardSummary = {
    total: 6,
    counts_by_status: { idea: 0, todo: 4, in_progress: 2, waiting: 0, validating: 0, done: 0 },
    overdue: 2,
    held_by_lia: 1,
    held_by_me: 3,
    needs_me: 0,
    owned: 6,
    max_tickets: 200,
    max_runs_per_ticket: 10,
    runs_total: 0,
    tokens_in: 0,
    tokens_out: 0,
    tokens_cache: 0,
    google_requests: 0,
    cost_eur: 0,
  };

  it('stands above the filters, open where the screen has room', () => {
    figures.summary = whole;
    render();

    expect(glance()).toHaveAttribute('open');
    const filters = screen.getByLabelText('workboard.filters.search');
    expect(
      glance()!.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      screen.getByRole('button', { name: /workboard\.summary\.tile_total/ })
    ).toHaveTextContent('6');
  });

  it('is folded on a phone, and reads nothing while it is', () => {
    viewport.wide = false;
    figures.summary = whole;
    render();

    expect(glance()).not.toHaveAttribute('open');
    expect(figures.reads).toEqual([]);
  });

  it('is folded inside another interface, whatever the screen', () => {
    figures.summary = whole;
    renderWithProviders(<WorkboardPage lng="fr" embedded />);

    expect(glance()).not.toHaveAttribute('open');
  });

  it('waits for the board before reading its figures', () => {
    board.firstLoad = true;
    figures.summary = whole;
    render();

    expect(figures.reads.length).toBeGreaterThan(0);
    expect(figures.reads.every(([enabled]) => enabled === false)).toBe(true);
    expect(screen.queryByRole('button', { name: /tile_total/ })).not.toBeInTheDocument();
  });

  it('narrows the board in place when a figure is pressed, and clears it from « on your board »', async () => {
    figures.summary = whole;
    const { user } = render();

    // The WHOLE filters, as the filter block holds them: the two it always
    // carries (who holds, which order) at their defaults, and the figure.
    const unfiltered = { assignee: 'all', sort: 'position' };
    await user.click(screen.getByRole('button', { name: /workboard\.summary\.tile_overdue/ }));
    expect(readBoard).toHaveBeenLastCalledWith({ ...unfiltered, overdue: true });
    await user.click(screen.getByRole('button', { name: /workboard\.columns\.todo/ }));
    // One figure at a time: the column replaces the lateness, it does not add to it.
    expect(readBoard).toHaveBeenLastCalledWith({ ...unfiltered, status: ['todo'] });
    await user.click(screen.getByRole('button', { name: /workboard\.summary\.tile_total/ }));
    expect(readBoard).toHaveBeenLastCalledWith(unfiltered);
    expect(hasFilters(readBoard.mock.calls.at(-1)?.[0] ?? {})).toBe(false);
  });

  it('re-reads its figures whenever the board under it is read again, whatever moved', () => {
    figures.summary = whole;
    const counts = { total: 6, countsByStatus: { todo: 4, in_progress: 2 } };
    Object.assign(board, counts, { tickets: [] });
    const view = render();
    const before = figures.reads.at(-1)?.[1];

    // The same rows drawn again: no reason to ask.
    view.rerender(<WorkboardPage lng="fr" />);
    expect(figures.reads.at(-1)?.[1]).toBe(before);

    // A payload that moved no count of the page — a category renamed, a due
    // time that passed, a ticket handed to LIA from another device.
    Object.assign(board, counts, { tickets: [] });
    view.rerender(<WorkboardPage lng="fr" />);
    expect(figures.reads.at(-1)?.[1]).not.toBe(before);
  });

  it('is not drawn where the instance switched the workboard off', () => {
    board.isUnavailable = true;
    render();

    expect(screen.queryByText('workboard.summary.title')).not.toBeInTheDocument();
  });
});

describe('the open panel is a place in the history, not a mode', () => {
  /** One ticket on the board, enough to have a card to open. */
  function ticket(): TicketRow {
    return makeTicket({
      id: 't1',
      owner_user_id: 'me',
      title: 'Réserver la salle',
      effective_assignee_id: 'me',
    });
  }

  beforeEach(() => {
    const row = ticket();
    Object.assign(board, {
      tickets: [row],
      total: 1,
      countsByStatus: { todo: 1 },
      column: (status: string) => (status === 'todo' ? [row] : []),
    });
  });

  it('opening a ticket PUSHES, so the back button closes it', async () => {
    // The panel is derived from the URL precisely so it can be linked and
    // dismissed by the browser. `replace` writes no history entry, so back
    // ejected the reader from the board instead of closing the panel — on
    // Android, where back IS the dismiss gesture.
    const user = userEvent.setup();
    render();
    await user.click(screen.getByRole('button', { name: 'Réserver la salle' }));
    expect(router.push).toHaveBeenCalledWith('/fr/dashboard/workboard?ticket=t1', {
      scroll: false,
    });
  });

  it('closing it REPLACES, so a dismissed panel does not stack an entry', async () => {
    const user = userEvent.setup();
    render('t1');
    await user.keyboard('{Escape}');
    expect(router.replace).toHaveBeenCalledWith('/fr/dashboard/workboard', { scroll: false });
    expect(router.push).not.toHaveBeenCalled();
  });

  it('keeps embedded filters and ticket navigation inside the host', async () => {
    const { user } = renderWithProviders(<WorkboardPage lng="fr" embedded />);
    router.push.mockClear();
    router.replace.mockClear();
    await user.type(screen.getByLabelText('workboard.filters.search'), 'salle');
    expect(router.replace).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Réserver la salle' }));
    expect(router.push).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeVisible();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByLabelText('workboard.filters.search')).toHaveValue('salle');
  });
});

describe('a board with categories', () => {
  const HOME = '11111111-1111-4111-8111-111111111111';
  const filed = makeTicket({
    id: 'h1',
    owner_user_id: 'me',
    title: 'Repeindre',
    effective_assignee_id: 'me',
    category_id: HOME,
  });
  const loose = makeTicket({
    id: 'u1',
    owner_user_id: 'me',
    title: 'À trier',
    effective_assignee_id: 'me',
    position: 1,
  });

  function withLanes() {
    Object.assign(board, {
      tickets: [filed, loose],
      total: 2,
      countsByStatus: { todo: 2 },
      column: (status: string) => (status === 'todo' ? [filed, loose] : []),
      lanes: [
        { category_id: null, name: null, owner_user_id: null, counts_by_status: { todo: 1 } },
        { category_id: HOME, name: 'Maison', owner_user_id: 'me', counts_by_status: { todo: 1 } },
      ],
    });
  }

  it('draws one lane per category, each card in its own', () => {
    withLanes();
    render();

    expect(screen.getByTestId(`lane-${HOME}`)).toHaveTextContent('Repeindre');
    expect(screen.getByTestId('lane-unfiled')).toHaveTextContent('À trier');
    expect(screen.getByTestId(`lane-${HOME}`)).not.toHaveTextContent('À trier');
  });

  it('keeps the flat board, and offers no lane filter, without a category', () => {
    Object.assign(board, {
      tickets: [loose],
      total: 1,
      countsByStatus: { todo: 1 },
      column: (status: string) => (status === 'todo' ? [loose] : []),
    });
    render();

    expect(screen.queryByTestId('lane-unfiled')).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'workboard.filters.category' })).toBeNull();
  });

  it('narrows the board to a lane through the filter', async () => {
    withLanes();
    const { user } = render();

    await user.click(screen.getByRole('combobox', { name: 'workboard.filters.category' }));
    await user.click(await screen.findByRole('option', { name: 'Maison' }));

    expect(readBoard).toHaveBeenLastCalledWith(expect.objectContaining({ category: [HOME] }));
  });

  it('opens the form in the lane whose « + » was pressed, and files the ticket there', async () => {
    withLanes();
    board.create.mockResolvedValue({ ok: true, errorCode: null });
    const { user } = render();

    await user.click(
      within(screen.getByTestId(`lane-${HOME}`)).getByRole('button', {
        name: 'workboard.lanes.add_ticket',
      })
    );
    const form = await screen.findByRole('dialog');
    expect(
      within(form).getByRole('combobox', { name: 'workboard.form.category' })
    ).toHaveTextContent('Maison');
    await user.type(within(form).getByLabelText('workboard.form.title'), 'Poncer');
    await user.click(within(form).getByRole('button', { name: 'workboard.actions.create' }));

    expect(board.create).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Poncer', category_id: HOME })
    );
  });

  it('starts the toolbar’s own « new ticket » in no lane', async () => {
    withLanes();
    const { user } = render();

    await user.click(screen.getAllByRole('button', { name: 'workboard.actions.create' })[0]);

    const form = await screen.findByRole('dialog');
    expect(
      within(form).getByRole('combobox', { name: 'workboard.form.category' })
    ).toHaveTextContent('workboard.categories.none');
  });
});

describe('administering the categories', () => {
  it('is offered on the toolbar at every size, even on a board with no ticket', () => {
    render();

    expect(screen.getByRole('button', { name: 'workboard.categories.manage' })).toBeInTheDocument();
  });

  it('reads the categories only once the dialog is opened', async () => {
    const { user } = render();
    expect(readCategories).toHaveBeenLastCalledWith(false);

    await user.click(screen.getByRole('button', { name: 'workboard.categories.manage' }));

    expect(readCategories).toHaveBeenLastCalledWith(true);
    expect(await screen.findByRole('dialog')).toHaveTextContent('workboard.categories.title');
  });

  it('re-reads the board after a category was created: its lanes changed', async () => {
    categories.create.mockResolvedValue({ ok: true, errorCode: null });
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'workboard.categories.manage' }));

    await user.type(
      await screen.findByRole('textbox', { name: 'workboard.categories.new_label' }),
      'Maison{Enter}'
    );

    await waitFor(() => expect(board.refetch).toHaveBeenCalled());
    expect(categories.create).toHaveBeenCalledWith({ name: 'Maison' });
  });

  it('is not offered while the instance has the workboard switched off', () => {
    board.isUnavailable = true;
    render();

    expect(screen.queryByRole('button', { name: 'workboard.categories.manage' })).toBeNull();
  });
});
