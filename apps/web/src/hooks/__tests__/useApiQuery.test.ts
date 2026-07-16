/**
 * Unit tests for the foundational `useApiQuery` data-fetching hook.
 *
 * Exercises the full lifecycle: fetch-on-mount, loading transitions,
 * success/error callbacks, ApiError vs generic Error normalization, the
 * AbortError silent path, the `enabled: false` gate, manual refetch, direct
 * setData, and the defensive missing-options guard. `api-client` and the
 * logger are mocked so no network or console noise leaks.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';
import { useApiQuery, type UseApiQueryOptions } from '../useApiQuery';

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

afterEach(() => vi.clearAllMocks());

describe('useApiQuery — success path', () => {
  it('fetches on mount, exposes data and clears loading', async () => {
    const onSuccess = vi.fn();
    mockApi.get.mockResolvedValueOnce({ id: 1 });

    const { result } = renderHook(() =>
      useApiQuery<{ id: number }>('/thing', { componentName: 'T', onSuccess })
    );

    // Loading is true synchronously (enabled defaults to true).
    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ id: 1 });
    expect(result.current.error).toBeNull();
    expect(onSuccess).toHaveBeenCalledWith({ id: 1 });
    expect(mockApi.get).toHaveBeenCalledWith('/thing', expect.objectContaining({ params: undefined }));
  });

  it('forwards params and config to the client', async () => {
    mockApi.get.mockResolvedValueOnce([]);
    renderHook(() =>
      useApiQuery('/list', {
        componentName: 'L',
        params: { page: 2 },
        config: { headers: { 'X-Test': '1' } },
      })
    );
    await waitFor(() => expect(mockApi.get).toHaveBeenCalled());
    expect(mockApi.get).toHaveBeenCalledWith(
      '/list',
      expect.objectContaining({ params: { page: 2 }, headers: { 'X-Test': '1' } })
    );
  });
});

describe('useApiQuery — error paths', () => {
  it('normalizes a generic Error and invokes onError', async () => {
    const onError = vi.fn();
    mockApi.get.mockRejectedValueOnce(new Error('boom'));

    const { result } = renderHook(() =>
      useApiQuery('/thing', { componentName: 'T', onError })
    );

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe('boom');
    expect(result.current.loading).toBe(false);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('preserves an ApiError instance (status kept)', async () => {
    mockApi.get.mockRejectedValueOnce(new ApiError('nope', 503));

    const { result } = renderHook(() => useApiQuery('/thing', { componentName: 'T' }));

    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
    expect((result.current.error as ApiError).status).toBe(503);
  });

  it('stays silent on an AbortError (no error, no onError)', async () => {
    const onError = vi.fn();
    mockApi.get.mockRejectedValueOnce(Object.assign(new Error('aborted'), { name: 'AbortError' }));

    const { result } = renderHook(() =>
      useApiQuery('/thing', { componentName: 'T', onError })
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });
});

describe('useApiQuery — control surface', () => {
  it('does not fetch when disabled', async () => {
    const { result } = renderHook(() =>
      useApiQuery('/thing', { componentName: 'T', enabled: false, initialData: 'seed' })
    );
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBe('seed');
    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it('refetch triggers another request', async () => {
    mockApi.get.mockResolvedValue('v');
    const { result } = renderHook(() => useApiQuery('/thing', { componentName: 'T' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockApi.get).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refetch();
    });
    expect(mockApi.get).toHaveBeenCalledTimes(2);
  });

  it('setData updates the cached value directly', async () => {
    mockApi.get.mockResolvedValueOnce('v');
    const { result } = renderHook(() => useApiQuery<string>('/thing', { componentName: 'T' }));
    await waitFor(() => expect(result.current.data).toBe('v'));

    act(() => result.current.setData('override'));
    expect(result.current.data).toBe('override');
  });

  it('throws a helpful error when options is missing', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() =>
      renderHook(() =>
        useApiQuery('/thing', undefined as unknown as UseApiQueryOptions<unknown>)
      )
    ).toThrow(/options is required/);
    spy.mockRestore();
  });
});
