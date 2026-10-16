/**
 * Recent outbound calls (A6).
 *
 * The endpoint was live and unread: a confirmed call disappeared from the UI
 * until a notification arrived, and a missed notification meant the outcome was
 * unreachable forever.
 *
 * Two things this surface must never do:
 *  - show the callee's phone number. The API omits it on purpose (encrypted at
 *    rest); nothing here may reintroduce it;
 *  - exist for nothing. A disabled feature or an account that never placed a
 *    call must render no empty shelf on an already long settings page.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, within, waitFor } from '@/__tests__/test-utils';
import type { TelephonyCallSummary } from '@/types/telephony';

const { useTelephonyCalls } = vi.hoisted(() => ({ useTelephonyCalls: vi.fn() }));

vi.mock('@/hooks/useTelephonyCalls', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useTelephonyCalls')>();
  return { ...actual, useTelephonyCalls };
});

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner-a' } }) }));

import TelephonyCallsSection from '../TelephonyCallsSection';

function call(overrides: Partial<TelephonyCallSummary> = {}): TelephonyCallSummary {
  return {
    id: 'c1',
    callee_display: 'Marie Dupont',
    objective: 'Demander si elle est libre mardi',
    status: 'completed',
    outcome: 'objective_met',
    summary: 'Marie est libre mardi après 14h.',
    debrief: null,
    call_seconds: 62,
    created_at: '2026-07-26T09:00:00Z',
    call_kind: 'third_party',
    call_mode: 'direct',
    relay_outcome: null,
    completed_at: '2026-07-26T09:01:02Z',
    ...overrides,
  };
}

function mockCalls(calls: TelephonyCallSummary[], overrides: Record<string, unknown> = {}) {
  useTelephonyCalls.mockReturnValue({
    calls,
    hasActiveCall: calls.some(c => c.status === 'dialing' || c.status === 'in_progress'),
    isLoading: false,
    isUnavailable: false,
    refetch: vi.fn(),
    error: null,
    ...overrides,
  });
}

describe('TelephonyCallsSection', () => {
  it('renders nothing when the feature is off', () => {
    mockCalls([], { isUnavailable: true });
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no call was ever placed', () => {
    // An empty shelf on an already long settings page is noise.
    mockCalls([]);
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('requests only the 10 most recent calls (owner arbitration 2026-07-30)', () => {
    mockCalls([call()]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(useTelephonyCalls).toHaveBeenCalledWith(true, 10);
  });

  it('shows what LIA was asked to do and what came of it, once the call is opened', async () => {
    mockCalls([call()]);
    const { user } = renderWithProviders(<TelephonyCallsSection lng="fr" />);

    await user.click(screen.getByText('Marie Dupont'));
    expect(screen.getByText('Demander si elle est libre mardi')).toBeInTheDocument();
    expect(screen.getByText('Marie est libre mardi après 14h.')).toBeInTheDocument();
  });

  it('never shows a phone number', () => {
    // The API omits it; this asserts nothing reintroduces one from elsewhere.
    mockCalls([call()]);
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(container.textContent ?? '').not.toMatch(/\+?\d[\d ().-]{7,}/);
  });

  it('marks a call that is still happening', () => {
    mockCalls([call({ status: 'in_progress', summary: null, outcome: null, call_seconds: null })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);

    expect(screen.getByText('settings.telephony.calls.status.in_progress')).toBeInTheDocument();
    // Announced politely — a call ending is worth saying, not worth interrupting.
    expect(screen.getByText('settings.telephony.calls.in_flight')).toBeInTheDocument();
  });

  it('says nothing about progress once every call has ended', () => {
    mockCalls([call()]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.queryByText('settings.telephony.calls.in_flight')).not.toBeInTheDocument();
  });

  it('renders a call that has no recap yet', () => {
    // `summary` is null while in flight and again after the retention purge.
    mockCalls([call({ summary: null, outcome: null, call_seconds: null })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByText('Marie Dupont')).toBeInTheDocument();
  });

  it('formats a duration in minutes past a minute', () => {
    mockCalls([call({ call_seconds: 125 })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByText(/2 min 5 s/)).toBeInTheDocument();
  });

  it('formats a short call in seconds', () => {
    mockCalls([call({ call_seconds: 48 })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByText(/48 s/)).toBeInTheDocument();
  });

  it('never renders an invalid date', () => {
    mockCalls([call({ created_at: 'not-a-date' })]);
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(container.textContent ?? '').not.toContain('Invalid Date');
  });

  it('lists several calls', () => {
    mockCalls([call(), call({ id: 'c2', callee_display: 'Le garage' })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });
});

describe('TelephonyCallsSection — calls with the person (phone as a channel)', () => {
  it('names the kind and the relay verdict of an owner call', () => {
    mockCalls([
      call({
        callee_display: 'Alex',
        call_kind: 'self',
        relay_outcome: 'waiting',
        outcome: 'objective_met',
      }),
    ]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByText('settings.telephony.calls.kind.self')).toBeInTheDocument();
    expect(screen.getByText('settings.telephony.calls.relay.waiting')).toBeInTheDocument();
    // The mode it RAN (ADR-301): a direct call says so; a stranger's call says nothing.
    expect(screen.getByText('settings.telephony.identity.call_mode.direct')).toBeInTheDocument();
  });

  it('names Live on an owner call that ran delegated, and never on a third-party call', () => {
    mockCalls([
      call({ id: 'live', callee_display: 'Alex', call_kind: 'self', call_mode: 'delegated' }),
      call({ id: 'errand', callee_display: 'Marie', call_kind: 'third_party' }),
    ]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getAllByText('settings.telephony.identity.call_mode.delegated')).toHaveLength(1);
    expect(screen.queryByText('settings.telephony.identity.call_mode.direct')).toBeNull();
  });

  it('draws the cumulated bill of a call that spent, and nothing otherwise', async () => {
    // Lot 8: live lookups, synthesis and relay under one run id — the calls
    // list reads the same summary the chat meter does.
    mockCalls([
      call({
        id: 'c-spent',
        usage: {
          tokens_in: 1200,
          tokens_out: 300,
          tokens_cache: 100,
          cost_eur: 0.0421,
          google_api_requests: 2,
        },
      }),
      call({ id: 'c-free', callee_display: 'Paul Martin' }),
    ]);
    const { user } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    await user.click(screen.getByText('Marie Dupont'));
    await user.click(screen.getByText('Paul Martin'));
    expect(screen.getAllByText('settings.telephony.calls.usage')).toHaveLength(1);
  });

  it('says nothing of the kind on a third-party call', () => {
    mockCalls([call()]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.queryByText(/settings\.telephony\.calls\.kind\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/settings\.telephony\.calls\.relay\./)).not.toBeInTheDocument();
  });
});

describe('TelephonyCallsSection — each call is a fold, closed by default', () => {
  const STARTED = '2026-07-26T09:00:00Z';

  it('folds every call and keeps the details unmounted until opened', () => {
    mockCalls([call(), call({ id: 'c2', callee_display: 'Le garage' })]);
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);

    const folds = container.querySelectorAll('details');
    expect(folds).toHaveLength(2);
    folds.forEach(fold => expect(fold.open).toBe(false));
    expect(screen.queryByText('Demander si elle est libre mardi')).not.toBeInTheDocument();
    expect(screen.queryByText('Marie est libre mardi après 14h.')).not.toBeInTheDocument();
  });

  it('says who, when, how long and how it went in the folded header', () => {
    mockCalls([call({ created_at: STARTED, call_seconds: 62 })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);

    const summary = screen.getByText('Marie Dupont').closest('summary');
    expect(summary).not.toBeNull();
    const header = within(summary as HTMLElement);
    const time = new Intl.DateTimeFormat('fr', { timeStyle: 'short' }).format(new Date(STARTED));
    expect(header.getByText(time)).toBeInTheDocument();
    expect(header.getByText('1 min 2 s')).toBeInTheDocument();
    expect(summary?.querySelector('time[datetime="2026-07-26T09:01:02Z"]')).not.toBeNull();
    // The badges ride the header, so the outcome reads without opening.
    expect(header.getByText('settings.telephony.calls.status.completed')).toBeInTheDocument();
    expect(header.getByText('settings.telephony.calls.outcome.objective_met')).toBeInTheDocument();
  });

  it('keeps an in-flight call folded with its status in the header', () => {
    mockCalls([call({ status: 'dialing', summary: null, outcome: null, call_seconds: null })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" />);

    const summary = screen.getByText('Marie Dupont').closest('summary') as HTMLElement;
    expect(
      within(summary).getByText('settings.telephony.calls.status.dialing')
    ).toBeInTheDocument();
    expect(summary.closest('details')?.open).toBe(false);
  });

  it('opens one call without opening the others', async () => {
    mockCalls([
      call(),
      call({ id: 'c2', callee_display: 'Le garage', objective: 'Prendre rendez-vous' }),
    ]);
    const { user } = renderWithProviders(<TelephonyCallsSection lng="fr" />);

    await user.click(screen.getByText('Le garage'));

    expect(screen.getByText('Prendre rendez-vous')).toBeInTheDocument();
    expect(screen.queryByText('Demander si elle est libre mardi')).not.toBeInTheDocument();
  });
});

describe('TelephonyCallsSection — timeline and recovery', () => {
  it('groups calls by dial date without losing or reordering any call', () => {
    mockCalls([
      call({ id: 'latest', callee_display: 'Le garage', created_at: '2026-07-27T10:00:00Z' }),
      call({ id: 'older', created_at: '2026-07-26T09:00:00Z' }),
      call({ id: 'unknown', callee_display: 'Date absente', created_at: 'broken' }),
    ]);
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(
      screen.getByRole('heading', { name: 'settings.telephony.calls.unknown_date', level: 4 })
    ).toBeInTheDocument();
    expect(
      Array.from(container.querySelectorAll('summary')).map(row => row.getAttribute('aria-label'))
    ).toEqual(['Le garage', 'Marie Dupont', 'Date absente']);
    expect(screen.getAllByRole('heading', { level: 4 })).toHaveLength(3);
  });
  it('announces first loading rather than a featureless blank pane', () => {
    mockCalls([], { isLoading: true });
    renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByRole('status', { name: 'common.loading' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('distinguishes an initial failure from an empty history and retries', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);
    mockCalls([], { error: new Error('offline'), refetch });
    const { user } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByRole('alert')).toHaveTextContent('settings.telephony.calls.load_error');
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
  it('keeps expanded content and focus during a failed refresh and recovery', async () => {
    mockCalls([call()]);
    const { user, rerender } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    const summary = screen.getByText('Marie Dupont').closest('summary')!;
    await user.click(summary);
    summary.focus();
    mockCalls([call()], { error: new Error('offline') });
    rerender(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByRole('alert')).toHaveTextContent('settings.telephony.calls.refresh_error');
    expect(summary.closest('details')).toHaveProperty('open', true);
    expect(summary).toHaveFocus();
    expect(screen.getByText('Marie est libre mardi après 14h.')).toBeInTheDocument();
    mockCalls([call({ summary: 'Nouvelle synthèse' })]);
    rerender(<TelephonyCallsSection lng="fr" />);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(summary.closest('details')).toHaveProperty('open', true);
    expect(screen.getByText('Nouvelle synthèse')).toBeInTheDocument();
  });
  it('preserves the existing row when a new day is prepended during refresh', async () => {
    mockCalls([call()]);
    const { user, rerender } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    const summary = screen.getByText('Marie Dupont').closest('summary')!;
    await user.click(summary);
    summary.focus();
    mockCalls([
      call({ id: 'new-day', callee_display: 'Le garage', created_at: '2026-07-27T09:00:00Z' }),
      call(),
    ]);
    rerender(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByText('Marie Dupont').closest('summary')).toBe(summary);
    expect(summary.closest('details')).toHaveProperty('open', true);
    expect(summary).toHaveFocus();
  });

  it('locks manual refresh until its read settles without dropping the focused button', async () => {
    let finish: () => void = () => undefined;
    const pending = new Promise<void>(resolve => {
      finish = resolve;
    });
    const refetch = vi.fn(() => pending);
    mockCalls([call()], { refetch });
    const { user } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    const button = screen.getByRole('button', { name: 'settings.telephony.calls.refresh' });
    await user.dblClick(button);
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute('aria-busy', 'true');
    finish();
    await waitFor(() => expect(button).not.toHaveAttribute('aria-busy'));
    expect(button).toHaveFocus();
  });

  it('places every draft action after all reported facts', async () => {
    mockCalls([
      call({
        structured_data: { proposed_datetime: 'mardi après-midi', additional_costs: '35 €' },
        debrief: {
          follow_up_tasks: ['Vérifier le devis'],
          uncertainties: ['Le prix final reste à confirmer'],
        },
      }),
    ]);
    const { user } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    await user.click(screen.getByText('Marie Dupont'));
    const finalFact = screen.getByText('Le prix final reste à confirmer');
    const firstAction = screen.getByRole('button', {
      name: 'settings.telephony.decisions.plan_meeting',
    });
    expect(
      finalFact.compareDocumentPosition(firstAction) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('keeps zero duration, never shows a negative or non-finite duration', () => {
    mockCalls([
      call({ id: 'zero', call_seconds: 0 }),
      call({ id: 'negative', callee_display: 'Négatif', call_seconds: -2 }),
      call({ id: 'invalid', callee_display: 'Invalide', call_seconds: NaN }),
    ]);
    const { container } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
    expect(screen.getByText('0 s')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/NaN|-2 s/);
  });
});
