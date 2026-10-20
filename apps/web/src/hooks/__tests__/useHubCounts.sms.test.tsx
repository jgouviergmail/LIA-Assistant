import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { useAuth, get } = vi.hoisted(() => ({ useAuth: vi.fn(), get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { useHubCounts } from '../useHubCounts';
import { publishApplicationResources } from '@/lib/application-resources';
const counts = {
  peer_messages: 0,
  proactive: 0,
  interests: 0,
  reminders: 0,
  scheduled: 0,
  offers: 0,
  workboard: 0,
  sms: 7,
};
beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  useAuth.mockReturnValue({ user: { id: 'owner' } });
});
it('hides the prior account counts immediately while the new account is loading', async () => {
  get.mockResolvedValueOnce(counts).mockImplementationOnce(() => new Promise(() => {}));
  const { result, rerender } = renderHook(() => useHubCounts());
  await waitFor(() => expect(result.current.counts?.sms).toBe(7));
  useAuth.mockReturnValue({ user: { id: 'other' } });
  rerender();
  expect(result.current.counts).toBeUndefined();
  await act(async () => {});
});
it('rereads on SMS reception or erasure and retains a source failure as unknown, never zero', async () => {
  get.mockResolvedValueOnce(counts).mockResolvedValueOnce({ ...counts, sms: null });
  const { result } = renderHook(() => useHubCounts());
  await waitFor(() => expect(result.current.counts?.sms).toBe(7));
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(result.current.counts?.sms).toBeNull());
});
