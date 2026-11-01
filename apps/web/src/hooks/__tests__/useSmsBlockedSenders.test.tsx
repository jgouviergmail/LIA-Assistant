/**
 * The blocked senders the « SMS » page manages: a page at a time, and back to
 * the first page whenever an SMS command lands (the source-owned `sms` resource).
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { useSmsBlockedSenders } from '../useSmsBlockedSenders';
import { publishApplicationResources } from '@/lib/application-resources';

beforeEach(() => {
  vi.clearAllMocks();
});

it('reads a page at a time, and the first page again after a source mutation', async () => {
  get.mockResolvedValue({
    blocks: [],
    total: 0,
    as_of: '2026-10-19T00:00:00Z',
    next_cursor: null,
  });
  const { result } = renderHook(() => useSmsBlockedSenders());
  await waitFor(() => expect(result.current.blocks.data).toBeDefined());
  expect(get.mock.calls[0][0]).toBe('/sms/blocked-senders');

  act(() => result.current.setCursor({ after_id: 'old', as_of: '2026-10-19T00:00:00Z' }));
  await waitFor(() =>
    expect(get.mock.calls.some(call => call[1]?.params?.after_id === 'old')).toBe(true)
  );
  act(() => publishApplicationResources('owner', new Set(['sms'])));

  await waitFor(() => expect(result.current.cursor).toBeUndefined());
  expect(get.mock.lastCall?.[1]?.params?.after_id).toBeUndefined();
});

it('reads nothing while it is not wanted', async () => {
  renderHook(() => useSmsBlockedSenders(false));
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });

  expect(get).not.toHaveBeenCalled();
});
