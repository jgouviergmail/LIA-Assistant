import { beforeEach, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { TelephonyCallSummary } from '@/types/telephony';

const { get, params, auth, recent } = vi.hoisted(() => ({
  get: vi.fn(),
  params: new URLSearchParams(),
  auth: vi.fn(),
  recent: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useSearchParams: () => params }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
vi.mock('@/hooks/useTelephonyCalls', () => ({
  useTelephonyCalls: recent,
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import TelephonyCallsSection from '../TelephonyCallsSection';
const id = '10000000-0000-4000-8000-000000000001';
const call: TelephonyCallSummary = {
  id,
  callee_display: 'Older Alice call',
  objective: 'Confirm appointment',
  summary: 'Tuesday confirmed',
  status: 'completed',
  outcome: 'objective_met',
  debrief: null,
  call_seconds: 62,
  created_at: '2026-01-01T09:00:00Z',
  completed_at: '2026-01-01T09:01:02Z',
  call_kind: 'third_party',
  call_mode: 'direct',
  relay_outcome: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  params.delete('call');
  auth.mockReturnValue({ user: { id: 'owner' } });
  recent.mockReturnValue({
    calls: [],
    isLoading: false,
    isUnavailable: false,
    error: null,
    refetch: vi.fn(),
    hasActiveCall: false,
  });
});

it('opens and focuses an exact linked call even outside the recent ten', async () => {
  params.set('call', id);
  get.mockResolvedValue(call);
  renderWithProviders(<TelephonyCallsSection lng="fr" />);
  expect(await screen.findByText('Tuesday confirmed')).toBeVisible();
  expect(
    screen.getByRole('heading', {
      level: 4,
      name: new Intl.DateTimeFormat('fr', { dateStyle: 'full' }).format(new Date(call.created_at)),
    })
  ).toBeVisible();
  const summary = screen.getByText('Older Alice call').closest('summary');
  expect(summary?.closest('details')).toHaveAttribute('open');
  await waitFor(() => expect(summary).toHaveFocus());
  expect(get.mock.calls[0][0]).toBe(`/telephony/calls/${id}`);
});

it('never steals focus after the person has moved while a slow call detail loads', async () => {
  params.set('call', id);
  let resolve: ((data: TelephonyCallSummary) => void) | undefined;
  get.mockImplementation(
    () =>
      new Promise(done => {
        resolve = done;
      })
  );
  renderWithProviders(
    <>
      <button>Other control</button>
      <TelephonyCallsSection lng="en" />
    </>
  );
  await waitFor(() => expect(get).toHaveBeenCalled());
  screen.getByRole('button', { name: 'Other control' }).focus();
  await act(async () => resolve?.(call));
  expect(await screen.findByText('Tuesday confirmed')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Other control' })).toHaveFocus();
});

it('reports a missing call, offers retry, and rejects invalid UUID links before IO', async () => {
  params.set('call', id);
  get.mockRejectedValueOnce(new Error('missing')).mockResolvedValue(call);
  const { user, rerender } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('settings.telephony.calls.load_error');
  await user.click(screen.getByRole('button', { name: 'common.retry' }));
  expect(await screen.findByText('Tuesday confirmed')).toBeVisible();
  const before = get.mock.calls.length;
  params.set('call', '../bad');
  rerender(<TelephonyCallsSection lng="fr" />);
  expect(screen.queryByText('Tuesday confirmed')).not.toBeInTheDocument();
  await act(async () => {});
  expect(get).toHaveBeenCalledTimes(before);
});

it('clears the previous account detail and rejects a late result on account switch', async () => {
  params.set('call', id);
  let resolve: ((data: TelephonyCallSummary) => void) | undefined;
  get
    .mockImplementationOnce(
      () =>
        new Promise(done => {
          resolve = done;
        })
    )
    .mockResolvedValue({ ...call, summary: 'Other account' });
  const { rerender } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
  await waitFor(() => expect(get).toHaveBeenCalledOnce());
  auth.mockReturnValue({ user: { id: 'other' } });
  rerender(<TelephonyCallsSection lng="fr" />);
  expect(await screen.findByText('Other account')).toBeVisible();
  await act(async () => resolve?.(call));
  expect(screen.queryByText('Tuesday confirmed')).not.toBeInTheDocument();
});

it('reuses a selected recent call without a duplicate read or row and refreshes older detail', async () => {
  params.set('call', id);
  recent.mockReturnValue({
    calls: [call],
    isLoading: false,
    isUnavailable: false,
    error: null,
    refetch: vi.fn(),
    hasActiveCall: false,
  });
  const { user, rerender } = renderWithProviders(<TelephonyCallsSection lng="fr" />);
  expect(await screen.findByText('Tuesday confirmed')).toBeVisible();
  expect(screen.getAllByText('Older Alice call')).toHaveLength(1);
  expect(get).not.toHaveBeenCalled();
  recent.mockReturnValue({
    calls: [],
    isLoading: false,
    isUnavailable: false,
    error: null,
    refetch: vi.fn(),
    hasActiveCall: false,
  });
  get.mockResolvedValue(call);
  rerender(<TelephonyCallsSection lng="fr" />);
  await waitFor(() => expect(get).toHaveBeenCalledOnce());
  await user.click(screen.getByRole('button', { name: 'settings.telephony.calls.refresh' }));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
});
