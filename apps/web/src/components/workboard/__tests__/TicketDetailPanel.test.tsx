/**
 * The panel says HOW to answer a confirmation (lot 7).
 *
 * LIA's comment carries the question and the preview; nothing else on the
 * screen turns « a comment box and a who-holds-it control » into a protocol
 * until the panel names it — and it must name it only while the ticket is
 * actually waiting on the person.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { TicketDetailPanel } from '@/components/workboard/TicketDetailPanel';
import type { TicketDetail, TicketRow } from '@/types/workboard';

const api = vi.hoisted(() => ({ detail: vi.fn() }));
vi.mock('@/lib/workboard/api', () => ({ workboardApi: api }));

// The usage block reads the header's own « show figures » switch, exactly as
// the chat's per-message line does.
const account = vi.hoisted(() => ({ value: { id: 'me', tokens_display_enabled: false } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account.value }) }));

function ticket(overrides: Partial<TicketRow> = {}): TicketRow {
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
    run_count: 1,
    run_claimed_at: null,
    last_run_at: '2026-09-09T10:00:00Z',
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

function detail(row: TicketRow): TicketDetail {
  return { ticket: row, children: [], comments: [], events: [] };
}

const handlers = {
  onClose: vi.fn(),
  onPatch: vi.fn(async (_id: string, _body: unknown) => ({ ok: true })),
  onComment: vi.fn(async () => ({ ok: true })),
  onRunNow: vi.fn(async () => ({ ok: true })),
  onDelete: vi.fn(),
};

function render() {
  return renderWithProviders(
    <TicketDetailPanel ticketId="t1" meId="me" peers={[]} lng="fr" {...handlers} />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('a ticket waiting for the person to confirm an action', () => {
  it('tells them how to answer', async () => {
    api.detail.mockResolvedValue(detail(ticket({ status: 'confirming' })));
    render();

    await waitFor(() => expect(screen.getByRole('note')).toBeInTheDocument());
    expect(screen.getByRole('note')).toHaveTextContent('workboard.detail.confirming_hint');
  });

  it('says nothing of the kind on any other ticket', async () => {
    api.detail.mockResolvedValue(detail(ticket({ status: 'waiting' })));
    render();

    await waitFor(() => expect(screen.getByText('Réserver la salle')).toBeInTheDocument());
    expect(screen.queryByRole('note')).toBeNull();
  });
});

describe('the due date, both ways', () => {
  it("reads back the day the instant falls on in the reader's zone", async () => {
    // Slicing the ISO string showed the UTC day: west of Greenwich the field
    // offered the day AFTER the one the person had picked.
    const stored = new Date('2026-12-24T23:59:59').toISOString();
    api.detail.mockResolvedValue(detail(ticket({ due_at: stored })));
    render();

    const field = await screen.findByLabelText('workboard.form.due_at');
    expect(field).toHaveValue('2026-12-24');
  });

  it('stores the END of the picked day, so it is not late on its own date', async () => {
    api.detail.mockResolvedValue(detail(ticket()));
    const { user } = render();

    const field = await screen.findByLabelText('workboard.form.due_at');
    await user.clear(field);
    await user.type(field, '2026-12-24');

    await waitFor(() => expect(handlers.onPatch).toHaveBeenCalled());
    const patch = handlers.onPatch.mock.calls.at(-1)?.[1] as { due_at?: string };
    expect(patch.due_at).toBeDefined();
    const instant = new Date(patch.due_at as string);
    expect(new Intl.DateTimeFormat('en-CA', { dateStyle: 'short' }).format(instant)).toBe(
      '2026-12-24'
    );
    expect(instant.getTime()).toBeGreaterThan(new Date('2026-12-24T12:00:00').getTime());
  });

  it('clears the deadline rather than storing an invalid instant', async () => {
    const stored = new Date('2026-12-24T23:59:59').toISOString();
    api.detail.mockResolvedValue(detail(ticket({ due_at: stored })));
    const { user } = render();

    const field = await screen.findByLabelText('workboard.form.due_at');
    await user.clear(field);

    await waitFor(() => expect(handlers.onPatch).toHaveBeenCalled());
    expect(handlers.onPatch.mock.calls.at(-1)?.[1]).toEqual({ clear_due_at: true });
  });
});

describe('what the ticket has cost', () => {
  it('says nothing while the reader has figures switched off', async () => {
    account.value = { id: 'me', tokens_display_enabled: false };
    api.detail.mockResolvedValue(
      detail(ticket({ run_count: 2, total_tokens_in: 1200, total_cost_eur: 0.42 }))
    );
    render();

    await waitFor(() => expect(screen.getByText('Réserver la salle')).toBeInTheDocument());
    expect(screen.queryByText('workboard.detail.usage')).toBeNull();
  });

  it("consolidates every run in the chat's own vocabulary", async () => {
    account.value = { id: 'me', tokens_display_enabled: true };
    api.detail.mockResolvedValue(
      detail(
        ticket({
          run_count: 3,
          total_tokens_in: 1200,
          total_tokens_out: 340,
          total_tokens_cache: 512,
          total_google_requests: 2,
          total_cost_eur: 0.42,
        })
      )
    );
    render();

    await waitFor(() => expect(screen.getByText('workboard.detail.usage')).toBeInTheDocument());
    // ONE line, the chat meter's legend in its order, the euros last — and no
    // « TOTAL »: the owner asked for IN · OUT · CACHE · GOOGLE · cost.
    const figures = ['IN', 'OUT', 'CACHE', 'GOOGLE'].map(label =>
      screen.getByText(new RegExp(`\\b${label}$`))
    );
    expect(figures[0]).toHaveTextContent(/1 200 IN|1,200 IN/);
    expect(figures[1]).toHaveTextContent(/340 OUT/);
    expect(figures[2]).toHaveTextContent(/512 CACHE/);
    expect(figures[3]).toHaveTextContent(/2 GOOGLE/);
    expect(screen.queryByText(/TOTAL/)).toBeNull();
    const line = figures[0].closest('p');
    expect(line).not.toBeNull();
    for (const figure of figures) expect(line).toContainElement(figure);
    expect(line).toHaveTextContent(/0,42|0\.42/);
    expect(screen.getByText('workboard.detail.usage_runs')).toBeInTheDocument();
  });

  it('says nothing on a ticket no run has touched', async () => {
    account.value = { id: 'me', tokens_display_enabled: true };
    api.detail.mockResolvedValue(detail(ticket()));
    render();

    await waitFor(() => expect(screen.getByText('Réserver la salle')).toBeInTheDocument());
    expect(screen.queryByText('workboard.detail.usage')).toBeNull();
  });
});

describe('the seven panels', () => {
  it('names every section as a region, in the order the owner listed them', async () => {
    // Details, settings, last run, cost, steps, comments, history — each a
    // labelled region, each on its own line (D70); a screen reader's outline
    // of the dialog is that list.
    account.value = { id: 'me', tokens_display_enabled: true };
    api.detail.mockResolvedValue(
      detail(
        ticket({
          run_count: 2,
          last_run_outcome: 'success',
          last_run_cost_eur: 0.01,
          total_tokens_in: 900,
          total_cost_eur: 0.02,
        })
      )
    );
    render();

    await waitFor(() => expect(screen.getByText('Réserver la salle')).toBeInTheDocument());
    const names = screen
      .getAllByRole('region')
      .map(region => region.getAttribute('aria-labelledby'))
      .map(id => (id ? document.getElementById(id)?.textContent : null));
    expect(names).toEqual([
      'workboard.detail.data',
      'workboard.detail.settings',
      'workboard.detail.last_run',
      'workboard.detail.usage',
      'workboard.detail.steps',
      'workboard.detail.comments',
      'workboard.detail.history',
    ]);
  });

  it('draws neither the last run nor the cost on a ticket no run has touched', async () => {
    account.value = { id: 'me', tokens_display_enabled: true };
    api.detail.mockResolvedValue(detail(ticket()));
    render();

    await waitFor(() => expect(screen.getByText('Réserver la salle')).toBeInTheDocument());
    expect(screen.queryByRole('region', { name: 'workboard.detail.last_run' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'workboard.detail.usage' })).toBeNull();
  });
});
