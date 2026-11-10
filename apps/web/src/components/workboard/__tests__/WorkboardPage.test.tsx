/**
 * The board screen: what it shows before the data, when there is none, and
 * when the instance switched the feature off.
 *
 * The two empty states are deliberately different: « nothing yet » invites a
 * first ticket, « no match » says the board is not empty — these filters are.
 * Confusing them sends a person looking for work that is right there.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, renderWithProviders, screen, userEvent } from '@/__tests__/test-utils';
import { handOff, setHandoffOwner } from '@/lib/workbench/handoff';
import { WorkboardPage } from '@/components/workboard/WorkboardPage';
import type { BoardFilters, TicketRow } from '@/types/workboard';

const board = vi.hoisted(() => ({
  tickets: [] as TicketRow[],
  countsByStatus: {} as Record<string, number>,
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
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipients: () => [] }));
const { account, notices } = vi.hoisted(() => ({
  account: { id: 'me' },
  notices: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account }) }));
vi.mock('sonner', () => ({ toast: notices }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }));

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
    total: 0,
    column: () => [],
    firstLoad: false,
    loading: false,
    error: null,
    isUnavailable: false,
  });
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
    const row: TicketRow = {
      id: 'a',
      owner_user_id: 'me',
      parent_id: null,
      title: 'A',
      description: null,
      status: 'todo',
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
      last_run_tokens_cache: null,
      last_run_google_requests: null,
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

describe('the open panel is a place in the history, not a mode', () => {
  /** One ticket on the board, enough to have a card to open. */
  function ticket(): TicketRow {
    return {
      id: 't1',
      owner_user_id: 'me',
      parent_id: null,
      title: 'Réserver la salle',
      description: null,
      status: 'todo',
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
      last_run_tokens_cache: null,
      last_run_google_requests: null,
      last_run_cost_eur: null,
      created_at: '2026-09-09T10:00:00Z',
      execution_mode: 'react',
    } as TicketRow;
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
