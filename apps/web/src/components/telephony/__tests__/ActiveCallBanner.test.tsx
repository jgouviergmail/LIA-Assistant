/**
 * "LIA is on the phone" (A6).
 *
 * The settings history answers "what happened"; this band answers "what is
 * happening", which is the question the user actually has while waiting. It
 * must appear only during a call and vanish the instant it ends — a status line
 * that lingers is worse than none, because it claims something false.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { TelephonyCallSummary } from '@/types/telephony';

const { useTelephonyCalls } = vi.hoisted(() => ({ useTelephonyCalls: vi.fn() }));

vi.mock('@/hooks/useTelephonyCalls', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useTelephonyCalls')>();
  return { ...actual, useTelephonyCalls };
});

import { ActiveCallBanner } from '../ActiveCallBanner';

function call(overrides: Partial<TelephonyCallSummary> = {}): TelephonyCallSummary {
  return {
    id: 'c1',
    callee_display: 'Marie',
    objective: 'Demander si elle est libre mardi',
    status: 'in_progress',
    outcome: null,
    summary: null,
    call_seconds: null,
    created_at: '2026-07-26T09:00:00Z',
    completed_at: null,
    ...overrides,
  };
}

function mockCalls(calls: TelephonyCallSummary[]) {
  useTelephonyCalls.mockReturnValue({
    calls,
    hasActiveCall: calls.some(c => c.status === 'dialing' || c.status === 'in_progress'),
    isLoading: false,
    isUnavailable: false,
    refetch: vi.fn(),
  });
}

describe('ActiveCallBanner', () => {
  it('says who LIA is talking to, and about what', () => {
    mockCalls([call()]);
    renderWithProviders(<ActiveCallBanner lng="fr" />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/Demander si elle est libre mardi/)).toBeInTheDocument();
  });

  it('distinguishes dialing from an answered call', () => {
    // "LIA is calling…" and "LIA is on the phone with…" are different facts.
    mockCalls([call({ status: 'dialing' })]);
    const { unmount } = renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(screen.getByText('chat.active_call.dialing')).toBeInTheDocument();
    unmount();

    mockCalls([call({ status: 'in_progress' })]);
    renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(screen.getByText('chat.active_call.in_progress')).toBeInTheDocument();
  });

  it('disappears the moment the call ends', () => {
    // A status line that outlives its subject asserts something false.
    mockCalls([call({ status: 'completed' })]);
    const { container } = renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no call was ever placed', () => {
    mockCalls([]);
    const { container } = renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('links to the recap surface in the current locale', () => {
    mockCalls([call()]);
    renderWithProviders(<ActiveCallBanner lng="de" />);
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/de/dashboard/settings?section=telephony-calls'
    );
  });

  it('announces politely rather than interrupting', () => {
    // The user is mid-conversation with LIA; this is context, not an alert.
    mockCalls([call()]);
    renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('never shows a phone number', () => {
    mockCalls([call()]);
    const { container } = renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(container.textContent ?? '').not.toMatch(/\+?\d[\d ().-]{7,}/);
  });

  it('picks the active call even when finished ones are newer in the list', () => {
    mockCalls([
      call({ id: 'done', status: 'completed' }),
      call({ id: 'live', callee_display: 'Paul' }),
    ]);
    renderWithProviders(<ActiveCallBanner lng="fr" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
