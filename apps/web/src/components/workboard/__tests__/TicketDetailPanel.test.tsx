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
import {
  TicketDetailPanel,
  type TicketDetailPanelProps,
} from '@/components/workboard/TicketDetailPanel';
import type { CategoryRow, TicketDetail, TicketRow } from '@/types/workboard';
import { makeTicket } from '@/__tests__/factories';

const api = vi.hoisted(() => ({ detail: vi.fn() }));
vi.mock('@/lib/workboard/api', () => ({ workboardApi: api }));

// The usage block reads the header's own « show figures » switch, exactly as
// the chat's per-message line does.
const account = vi.hoisted(() => ({ value: { id: 'me', tokens_display_enabled: false } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account.value }) }));

function ticket(overrides: Partial<TicketRow> = {}): TicketRow {
  return makeTicket({
    id: 't1',
    owner_user_id: 'me',
    title: 'Réserver la salle',
    effective_assignee_id: 'me',
    run_count: 1,
    last_run_at: '2026-09-09T10:00:00Z',
    ...overrides,
  });
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

function render(extra: Partial<TicketDetailPanelProps> = {}) {
  return renderWithProviders(
    <TicketDetailPanel ticketId="t1" meId="me" peers={[]} lng="fr" {...handlers} {...extra} />
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

describe('the category of a ticket', () => {
  // The category is the OWNER's: they file the ticket from here wherever
  // nothing drags; whoever holds it for them reads the lane and changes nothing.
  const CATEGORIES: CategoryRow[] = [
    { id: 'home', owner_user_id: 'me', name: 'Maison', position: 0, ticket_count: 1 },
    { id: 'work', owner_user_id: 'me', name: 'Travail', position: 1, ticket_count: 0 },
  ];
  const list = () => screen.queryByRole('combobox', { name: 'workboard.form.category' });

  it('lets the owner file the ticket under another of their categories', async () => {
    api.detail.mockResolvedValue(detail(ticket({ category_id: 'home' })));
    const { user } = render({ categories: CATEGORIES });

    await waitFor(() => expect(list()).toHaveTextContent('Maison'));
    await user.click(screen.getByRole('combobox', { name: 'workboard.form.category' }));
    await user.click(await screen.findByRole('option', { name: 'Travail' }));

    expect(handlers.onPatch).toHaveBeenCalledWith('t1', { category_id: 'work' });
  });

  it('un-files it explicitly: null and « unchanged » are one wire value', async () => {
    api.detail.mockResolvedValue(detail(ticket({ category_id: 'home' })));
    const { user } = render({ categories: CATEGORIES });

    await waitFor(() => expect(list()).not.toBeNull());
    await user.click(screen.getByRole('combobox', { name: 'workboard.form.category' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.categories.none' }));

    expect(handlers.onPatch).toHaveBeenCalledWith('t1', { clear_category: true });
  });

  it('asks nothing of an owner who has no category', async () => {
    api.detail.mockResolvedValue(detail(ticket()));
    render();

    await screen.findByLabelText('workboard.form.due_at');
    expect(list()).toBeNull();
    expect(screen.queryByTestId('category-badge')).toBeNull();
  });

  it('shows a holder the owner’s lane, as a fact and not as a control', async () => {
    api.detail.mockResolvedValue(detail(ticket({ owner_user_id: 'peer', category_id: 'theirs' })));
    render({
      categories: CATEGORIES,
      categoryName: id => (id === 'theirs' ? 'Chantier' : undefined),
    });

    expect(await screen.findByTestId('category-badge')).toHaveTextContent('Chantier');
    expect(list()).toBeNull();
  });

  it('shows a holder nothing for a ticket its owner filed under nothing', async () => {
    api.detail.mockResolvedValue(detail(ticket({ owner_user_id: 'peer', category_id: null })));
    render({ categories: CATEGORIES, categoryName: () => undefined });

    await screen.findByLabelText('workboard.form.due_at');
    expect(list()).toBeNull();
    expect(screen.queryByTestId('category-badge')).toBeNull();
  });
});
