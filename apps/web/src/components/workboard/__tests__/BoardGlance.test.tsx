/**
 * BoardGlance — the board at a glance, above its own filters (ADR-276,
 * amendment 2026-11-11).
 *
 * It used to be a settings section, each figure a LINK into the board. On the
 * board itself a figure is a BUTTON that narrows the board in place, the block
 * folds — folded on arrival where the screen is small — and a folded block
 * asks the server nothing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';
import type { BoardFilters, BoardSummary, LaneRow } from '@/types/workboard';

const state = vi.hoisted(() => ({
  summary: undefined as BoardSummary | undefined,
  error: false,
  reads: [] as Array<[boolean, string]>,
}));
const account = vi.hoisted(() => ({ user: { id: 'me', tokens_display_enabled: true } }));

vi.mock('@/hooks/useWorkboardSummary', () => ({
  useWorkboardSummary: (enabled: boolean, stamp: string) => {
    state.reads.push([enabled, stamp]);
    return { summary: state.summary, loading: false, error: state.error };
  },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account.user }) }));

import { BoardGlance, type BoardGlanceProps } from '@/components/workboard/BoardGlance';

const HOME = '11111111-1111-4111-8111-111111111111';

function summary(overrides: Partial<BoardSummary> = {}): BoardSummary {
  return {
    total: 6,
    counts_by_status: {
      idea: 1,
      todo: 3,
      in_progress: 0,
      waiting: 0,
      confirming: 0,
      validating: 1,
      done: 1,
    },
    overdue: 2,
    held_by_lia: 1,
    held_by_me: 3,
    needs_me: 2,
    owned: 5,
    max_tickets: 200,
    max_runs_per_ticket: 10,
    runs_total: 4,
    tokens_in: 1200,
    tokens_out: 300,
    tokens_cache: 100,
    google_requests: 2,
    cost_eur: 0.42,
    ...overrides,
  };
}

function glance(overrides: Partial<BoardGlanceProps> = {}) {
  const onNarrow = vi.fn<(narrowing: BoardFilters) => void>();
  const props: BoardGlanceProps = {
    lng: 'fr',
    defaultOpen: true,
    ready: true,
    stamp: 'first',
    onNarrow,
    ...overrides,
  };
  const view = render(<BoardGlance {...props} />);
  return { onNarrow, props, ...view };
}

const title = () => screen.getByText('workboard.summary.title');
const figure = (label: string) => screen.getByRole('button', { name: new RegExp(label) });

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  useWorkboardLanesStore.setState({ collapsed: [], summaryOpen: null });
  state.summary = summary();
  state.error = false;
  state.reads = [];
  account.user = { id: 'me', tokens_display_enabled: true };
});

describe('BoardGlance — folding', () => {
  it('stays folded on arrival where the screen is small, and asks the server nothing', () => {
    glance({ defaultOpen: false });

    expect(title().closest('details')).not.toHaveAttribute('open');
    // What it holds is said while it is shut.
    expect(screen.getByText('workboard.summary.hint')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /tile_total/ })).toBeNull();
    expect(state.reads).toEqual([]);
  });

  it('is open on arrival where the screen has room', () => {
    glance({ defaultOpen: true });

    expect(title().closest('details')).toHaveAttribute('open');
    expect(figure('workboard.summary.tile_total')).toHaveTextContent('6');
    expect(state.reads[0]).toEqual([true, 'first']);
  });

  it('remembers on this device what the person chose, against the default', async () => {
    const user = userEvent.setup();
    const first = glance({ defaultOpen: true });
    await user.click(title());

    expect(title().closest('details')).not.toHaveAttribute('open');
    expect(useWorkboardLanesStore.getState().summaryOpen).toBe(false);
    first.unmount();

    // A later visit, same device, same wide screen: it stays as it was left.
    glance({ defaultOpen: true });
    expect(title().closest('details')).not.toHaveAttribute('open');

    // …and a phone that was opened once stays open.
    await user.click(title());
    expect(useWorkboardLanesStore.getState().summaryOpen).toBe(true);
  });

  it('records a choice only when the person makes one, never the state it arrived in', () => {
    // A browser fires `toggle` on a <details> that is merely CREATED open, and
    // again when the screen's size opens it: neither is somebody's choice, and
    // storing it would pin the block open on this device's small screen too.
    glance({ defaultOpen: true });
    const block = title().closest('details')!;
    expect(block.open).toBe(true);

    fireEvent(block, new Event('toggle'));

    expect(useWorkboardLanesStore.getState().summaryOpen).toBeNull();
  });

  it('waits for the board under it before reading anything', () => {
    glance({ ready: false });

    expect(state.reads.every(([enabled]) => enabled === false)).toBe(true);
  });

  it('re-reads its figures when the board says they may have moved', () => {
    const { rerender, props } = glance();
    rerender(<BoardGlance {...props} stamp="second" />);

    expect(state.reads.at(-1)).toEqual([true, 'second']);
  });
});

describe('BoardGlance — a figure narrows the board in place', () => {
  it('narrows to the figure pressed, and « on your board » clears every filter', async () => {
    const user = userEvent.setup();
    const { onNarrow } = glance();

    await user.click(figure('workboard.summary.tile_overdue'));
    expect(onNarrow).toHaveBeenLastCalledWith({ overdue: true });
    await user.click(figure('workboard.summary.tile_lia'));
    expect(onNarrow).toHaveBeenLastCalledWith({ assignee: 'lia' });
    // « My tickets »: what the person holds, never the « needs me » set (2).
    expect(figure('workboard.summary.tile_mine')).toHaveTextContent('3');
    await user.click(figure('workboard.summary.tile_mine'));
    expect(onNarrow).toHaveBeenLastCalledWith({ assignee: 'me' });
    await user.click(figure('workboard.summary.tile_total'));
    expect(onNarrow).toHaveBeenLastCalledWith({});
  });

  it('lists the columns with their exact counts, the conditional one only when it holds something', async () => {
    const user = userEvent.setup();
    const { onNarrow } = glance();

    const columns = screen.getByRole('list', { name: 'workboard.summary.by_column' });
    expect(within(columns).getAllByRole('button')).toHaveLength(6);
    expect(within(columns).queryByRole('button', { name: /confirming/ })).toBeNull();
    const todo = within(columns).getByRole('button', { name: /workboard\.columns\.todo/ });
    expect(todo).toHaveTextContent('3');
    await user.click(todo);
    expect(onNarrow).toHaveBeenLastCalledWith({ status: ['todo'] });
  });

  it('draws « to confirm » as soon as one ticket waits there', () => {
    state.summary = summary({
      counts_by_status: { ...summary().counts_by_status, confirming: 1 },
    });
    glance();

    expect(
      within(screen.getByRole('list', { name: 'workboard.summary.by_column' })).getAllByRole(
        'button'
      )
    ).toHaveLength(7);
  });

  it('counts each lane over the whole board and narrows to it, or to what is filed under nothing', async () => {
    const lanes: LaneRow[] = [
      { category_id: null, name: null, owner_user_id: null, counts_by_status: { todo: 2 } },
      {
        category_id: HOME,
        name: 'Maison',
        owner_user_id: 'me',
        counts_by_status: { todo: 3, done: 1 },
      },
    ];
    state.summary = summary({ lanes });
    const user = userEvent.setup();
    const { onNarrow } = glance();

    const list = screen.getByRole('list', { name: 'workboard.summary.by_category' });
    const home = within(list).getByRole('button', { name: /Maison/ });
    // 3 + 1: every column of the lane, never a page.
    expect(home).toHaveTextContent('4');
    await user.click(home);
    expect(onNarrow).toHaveBeenLastCalledWith({ category: [HOME] });
    const unfiled = within(list).getByRole('button', { name: /workboard\.lanes\.unfiled/ });
    expect(unfiled).toHaveTextContent('2');
    await user.click(unfiled);
    expect(onNarrow).toHaveBeenLastCalledWith({ uncategorized: true });
  });

  it('says nothing of categories to an account that has none, or to an API that predates them', () => {
    state.summary = summary({ lanes: [] });
    const first = glance();
    expect(screen.queryByRole('list', { name: 'workboard.summary.by_category' })).toBeNull();
    first.unmount();

    state.summary = summary();
    glance();
    expect(screen.queryByRole('list', { name: 'workboard.summary.by_category' })).toBeNull();
  });
});

describe('BoardGlance — what the account owns, costs and is waited on for', () => {
  it('shows what the account owns against the published cap', () => {
    glance();

    const gauge = screen.getByRole('progressbar', { name: 'workboard.summary.capacity_label' });
    expect(gauge).toHaveAttribute('aria-valuenow', '5');
    expect(gauge).toHaveAttribute('aria-valuemax', '200');
  });

  it("shows the cost in the meter's vocabulary, under the header's switch only", () => {
    const first = glance();
    expect(screen.getByText(/1 200 IN|1,200 IN/)).toBeInTheDocument();
    expect(screen.getByText(/0,42|0\.42/)).toBeInTheDocument();
    expect(screen.getByText('workboard.summary.runs')).toBeInTheDocument();
    first.unmount();

    account.user = { id: 'me', tokens_display_enabled: false };
    glance();
    expect(screen.queryByText('workboard.summary.cost')).toBeNull();
  });

  it('says nothing of the cost while no run has happened', () => {
    state.summary = summary({ runs_total: 0 });
    glance();

    expect(screen.queryByText('workboard.summary.cost')).toBeNull();
  });

  it('tells the person what waits on them, from the same figures', () => {
    const first = glance();
    expect(screen.getByText('workboard.summary.needs_you')).toBeInTheDocument();
    first.unmount();

    state.summary = summary({ needs_me: 0 });
    glance();
    expect(screen.getByText('workboard.summary.nothing_waiting')).toBeInTheDocument();
  });

  it('shows no figure it does not know, and says so when the read was refused', () => {
    state.summary = undefined;
    const first = glance();
    expect(screen.queryByRole('button', { name: /tile_total/ })).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    first.unmount();

    state.error = true;
    glance();
    expect(screen.getByRole('alert')).toHaveTextContent('workboard.summary.unavailable');
    expect(screen.queryByRole('button', { name: /tile_total/ })).toBeNull();
  });

  it('keeps the figures it last read when a later read fails', () => {
    // The block is read again whenever the board is — every half minute while
    // it is open. A lost second must not turn known figures into an alert.
    state.error = true;
    glance();

    expect(figure('workboard.summary.tile_total')).toHaveTextContent('6');
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
