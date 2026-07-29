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

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { TelephonyCallSummary } from '@/types/telephony';

const { useTelephonyCalls } = vi.hoisted(() => ({ useTelephonyCalls: vi.fn() }));

vi.mock('@/hooks/useTelephonyCalls', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useTelephonyCalls')>();
  return { ...actual, useTelephonyCalls };
});

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
    ...overrides,
  });
}

describe('TelephonyCallsSection', () => {
  it('renders nothing when the feature is off', () => {
    mockCalls([], { isUnavailable: true });
    const { container } = renderWithProviders(
      <TelephonyCallsSection lng="fr" collapsible={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no call was ever placed', () => {
    // An empty shelf on an already long settings page is noise.
    mockCalls([]);
    const { container } = renderWithProviders(
      <TelephonyCallsSection lng="fr" collapsible={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows what LIA was asked to do and what came of it', () => {
    mockCalls([call()]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);

    expect(screen.getByText('Marie Dupont')).toBeInTheDocument();
    expect(screen.getByText('Demander si elle est libre mardi')).toBeInTheDocument();
    expect(screen.getByText('Marie est libre mardi après 14h.')).toBeInTheDocument();
  });

  it('never shows a phone number', () => {
    // The API omits it; this asserts nothing reintroduces one from elsewhere.
    mockCalls([call()]);
    const { container } = renderWithProviders(
      <TelephonyCallsSection lng="fr" collapsible={false} />
    );
    expect(container.textContent ?? '').not.toMatch(/\+?\d[\d ().-]{7,}/);
  });

  it('marks a call that is still happening', () => {
    mockCalls([call({ status: 'in_progress', summary: null, outcome: null, call_seconds: null })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);

    expect(screen.getByText('settings.telephony.calls.status.in_progress')).toBeInTheDocument();
    // Announced politely — a call ending is worth saying, not worth interrupting.
    expect(screen.getByText('settings.telephony.calls.in_flight')).toBeInTheDocument();
  });

  it('says nothing about progress once every call has ended', () => {
    mockCalls([call()]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);
    expect(screen.queryByText('settings.telephony.calls.in_flight')).not.toBeInTheDocument();
  });

  it('renders a call that has no recap yet', () => {
    // `summary` is null while in flight and again after the retention purge.
    mockCalls([call({ summary: null, outcome: null, call_seconds: null })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);
    expect(screen.getByText('Marie Dupont')).toBeInTheDocument();
  });

  it('formats a duration in minutes past a minute', () => {
    mockCalls([call({ call_seconds: 125 })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);
    expect(screen.getByText(/2 min 5 s/)).toBeInTheDocument();
  });

  it('formats a short call in seconds', () => {
    mockCalls([call({ call_seconds: 48 })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);
    expect(screen.getByText(/48 s/)).toBeInTheDocument();
  });

  it('never renders an invalid date', () => {
    mockCalls([call({ created_at: 'not-a-date' })]);
    const { container } = renderWithProviders(
      <TelephonyCallsSection lng="fr" collapsible={false} />
    );
    expect(container.textContent ?? '').not.toContain('Invalid Date');
  });

  it('lists several calls', () => {
    mockCalls([call(), call({ id: 'c2', callee_display: 'Le garage' })]);
    renderWithProviders(<TelephonyCallsSection lng="fr" collapsible={false} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });
});
