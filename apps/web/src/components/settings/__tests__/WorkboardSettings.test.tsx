/**
 * WorkboardSettings (ADR-276, lot 18) — the board at a glance: every figure
 * from the server's aggregate, every figure a link into the narrowed board,
 * the cap published, the cost under the header's switch, the door kept.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import type { BoardSummary } from '@/types/workboard';

const config = vi.hoisted(() => ({ value: { features: { workboard_enabled: true } } }));
const state = vi.hoisted(() => ({
  summary: undefined as BoardSummary | undefined,
  error: false,
}));
const account = vi.hoisted(() => ({ user: { id: 'me', tokens_display_enabled: true } }));
const push = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: config.value, loading: false, error: null }),
}));
vi.mock('@/hooks/useWorkboardSummary', () => ({
  useWorkboardSummary: () => ({ summary: state.summary, loading: false, error: state.error }),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account.user }) }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));

import { WorkboardSettings } from '@/components/settings/WorkboardSettings';

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

beforeEach(() => {
  vi.clearAllMocks();
  config.value = { features: { workboard_enabled: true } };
  state.summary = summary();
  state.error = false;
  account.user = { id: 'me', tokens_display_enabled: true };
});

describe('WorkboardSettings', () => {
  it('renders nothing where the instance does not run the board', () => {
    config.value = { features: { workboard_enabled: false } };
    const { container } = render(<WorkboardSettings lng="fr" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('links every figure into the board narrowed to it', () => {
    render(<WorkboardSettings lng="fr" />);

    const tile = (label: string) => screen.getByRole('link', { name: new RegExp(label) });
    expect(tile('settings.workboard.tile_total')).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard'
    );
    expect(tile('settings.workboard.tile_total')).toHaveTextContent('6');
    expect(tile('settings.workboard.tile_overdue')).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard?overdue=1'
    );
    expect(tile('settings.workboard.tile_overdue')).toHaveTextContent('2');
    expect(tile('settings.workboard.tile_lia')).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard?assignee=lia'
    );
    expect(tile('settings.workboard.tile_needs_me')).toHaveTextContent('2');
  });

  it('lists the columns with their exact counts, the conditional one only when it holds something', () => {
    render(<WorkboardSettings lng="fr" />);

    const columns = screen.getByRole('list', { name: 'settings.workboard.by_column' });
    const chips = within(columns).getAllByRole('link');
    expect(chips).toHaveLength(6);
    expect(within(columns).getByRole('link', { name: /workboard\.columns\.todo/ })).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard?status=todo'
    );
    expect(
      within(columns).getByRole('link', { name: /workboard\.columns\.todo/ })
    ).toHaveTextContent('3');
    expect(within(columns).queryByRole('link', { name: /confirming/ })).toBeNull();
  });

  it('draws « to confirm » as soon as one ticket waits there', () => {
    state.summary = summary({
      counts_by_status: { ...summary().counts_by_status, confirming: 1 },
    });
    render(<WorkboardSettings lng="fr" />);

    expect(
      within(screen.getByRole('list', { name: 'settings.workboard.by_column' })).getAllByRole(
        'link'
      )
    ).toHaveLength(7);
  });

  it('shows what the account owns against the published cap', () => {
    render(<WorkboardSettings lng="fr" />);

    const gauge = screen.getByRole('progressbar', { name: 'settings.workboard.capacity_label' });
    expect(gauge).toHaveAttribute('aria-valuenow', '5');
    expect(gauge).toHaveAttribute('aria-valuemax', '200');
  });

  it("shows the cost in the meter's vocabulary, under the header's switch only", () => {
    render(<WorkboardSettings lng="fr" />);
    expect(screen.getByText(/1 200 IN|1,200 IN/)).toBeInTheDocument();
    expect(screen.getByText(/0,42|0\.42/)).toBeInTheDocument();
    expect(screen.getByText('settings.workboard.runs')).toBeInTheDocument();

    account.user = { id: 'me', tokens_display_enabled: false };
    render(<WorkboardSettings lng="fr" />);
    expect(screen.getAllByText(/IN$/)).toHaveLength(1);
  });

  it('says nothing of the cost while no run has happened', () => {
    state.summary = summary({ runs_total: 0 });
    render(<WorkboardSettings lng="fr" />);

    expect(screen.queryByText('settings.workboard.cost')).toBeNull();
  });

  it('tells the person what waits on them, from the same figures', () => {
    render(<WorkboardSettings lng="fr" />);
    expect(screen.getByText('settings.workboard.needs_you')).toBeInTheDocument();

    state.summary = summary({ needs_me: 0 });
    render(<WorkboardSettings lng="fr" />);
    expect(screen.getByText('settings.workboard.nothing_waiting')).toBeInTheDocument();
  });

  it('keeps the door while the figures are unknown or refused', () => {
    state.summary = undefined;
    state.error = true;
    render(<WorkboardSettings lng="fr" />);

    expect(screen.queryByText('settings.workboard.glance')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'settings.workboard.open_board' }));
    expect(push).toHaveBeenCalledWith('/dashboard/workboard');
  });
});
