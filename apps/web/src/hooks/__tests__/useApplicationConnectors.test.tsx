import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get } };
});
import { useApplicationConnectors } from '../useApplicationConnectors';

const saved = { connectors: [{ id: 'saved-one', connector_type: 'google_gmail', status: 'active', created_at: '2026-10-07T00:00:00Z' }] };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

it('reads the canonical list after an owned native unlink without trusting the cache', async () => {
  const { result } = renderHook(() => useApplicationConnectors());
  await waitFor(() => expect(result.current.data).toEqual(saved));
  expect(get.mock.calls[0][0]).toBe('/connectors?fresh=true');
  get.mockResolvedValueOnce({ connectors: [] });
  act(() => publishApplicationResources('two', new Set(['connectors'])));
  expect(get).toHaveBeenCalledTimes(1);
  act(() => publishApplicationResources('one', new Set(['connectors'])));
  await waitFor(() => expect(result.current.data?.connectors).toEqual([]));
});

it('preserves known cards when a reread fails and does not leak updates across accounts', async () => {
  const { result, rerender } = renderHook(() => useApplicationConnectors());
  await waitFor(() => expect(result.current.data).toEqual(saved));
  get.mockRejectedValueOnce(new Error('offline'));
  act(() => publishApplicationResources('one', new Set(['connectors'])));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  expect(result.current.data).toEqual(saved);
  const obsolete = result.current.setData;
  useAuth.mockReturnValue({ user: { id: 'two' } });
  get.mockImplementationOnce(() => new Promise(() => {}));
  rerender();
  expect(result.current.data).toBeUndefined();
  act(() => obsolete(saved));
  expect(result.current.data).toBeUndefined();
});
