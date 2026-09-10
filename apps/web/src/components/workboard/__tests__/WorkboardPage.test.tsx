/**
 * The board screen: what it shows before the data, when there is none, and
 * when the instance switched the feature off.
 *
 * The two empty states are deliberately different: « nothing yet » invites a
 * first ticket, « no match » says the board is not empty — these filters are.
 * Confusing them sends a person looking for work that is right there.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, userEvent } from '@/__tests__/test-utils';
import { WorkboardPage } from '@/components/workboard/WorkboardPage';
import type { TicketRow } from '@/types/workboard';

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
vi.mock('@/hooks/useWorkboard', () => ({ useWorkboard: () => board }));
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipients: () => [] }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'me' } }) }));
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

describe('before anything has been read', () => {
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
});
