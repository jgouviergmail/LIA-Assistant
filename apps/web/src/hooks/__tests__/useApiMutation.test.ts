/**
 * Unit tests for the foundational `useApiMutation` hook.
 *
 * Covers every HTTP method branch (POST/PUT/PATCH/DELETE incl. the DELETE body
 * serialization), success data + onSuccess, ApiError vs generic Error
 * normalization with rethrow, onError, loading transitions, reset(), and the
 * defensive missing-options guard. `api-client` and the logger are mocked.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';
import { useApiMutation, type UseApiMutationOptions } from '../useApiMutation';

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

describe('useApiMutation — method routing', () => {
  it('POST forwards (endpoint, data, config) and returns the response', async () => {
    mockApi.post.mockResolvedValueOnce({ id: 1 });
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useApiMutation<{ name: string }, { id: number }>({
        method: 'POST',
        componentName: 'F',
        onSuccess,
      })
    );

    let returned: { id: number } | undefined;
    await act(async () => {
      returned = await result.current.mutate('/users', { name: 'x' });
    });

    expect(mockApi.post).toHaveBeenCalledWith('/users', { name: 'x' }, undefined);
    expect(returned).toEqual({ id: 1 });
    expect(result.current.data).toEqual({ id: 1 });
    expect(onSuccess).toHaveBeenCalledWith({ id: 1 });
    expect(result.current.loading).toBe(false);
  });

  it('PUT and PATCH route to the matching client method', async () => {
    mockApi.put.mockResolvedValueOnce('put-ok');
    const { result: put } = renderHook(() => useApiMutation({ method: 'PUT', componentName: 'F' }));
    await act(async () => {
      await put.current.mutate('/e', { a: 1 });
    });
    expect(mockApi.put).toHaveBeenCalledWith('/e', { a: 1 }, undefined);

    mockApi.patch.mockResolvedValueOnce('patch-ok');
    const { result: patch } = renderHook(() =>
      useApiMutation({ method: 'PATCH', componentName: 'F' })
    );
    await act(async () => {
      await patch.current.mutate('/e', { a: 2 });
    });
    expect(mockApi.patch).toHaveBeenCalledWith('/e', { a: 2 }, undefined);
  });

  it('DELETE serializes the optional body into config', async () => {
    mockApi.delete.mockResolvedValue(undefined);
    const { result } = renderHook(() => useApiMutation({ method: 'DELETE', componentName: 'F' }));

    await act(async () => {
      await result.current.mutate('/e/1', { reason: 'x' });
    });
    expect(mockApi.delete).toHaveBeenCalledWith('/e/1', { body: JSON.stringify({ reason: 'x' }) });

    await act(async () => {
      await result.current.mutate('/e/2');
    });
    expect(mockApi.delete).toHaveBeenLastCalledWith('/e/2', { body: undefined });
  });
});

describe('useApiMutation — error handling', () => {
  it('normalizes a generic Error, calls onError and rethrows', async () => {
    mockApi.post.mockRejectedValueOnce(new Error('kaboom'));
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useApiMutation({ method: 'POST', componentName: 'F', onError })
    );

    // Catch inside act() so the error-path state updates flush before asserting;
    // capture the thrown value to prove the mutation rethrows.
    let thrown: unknown;
    await act(async () => {
      await result.current.mutate('/e', {}).catch(e => {
        thrown = e;
      });
    });

    expect((thrown as Error).message).toBe('kaboom');
    expect(onError).toHaveBeenCalledTimes(1);
    expect(result.current.error?.message).toBe('kaboom');
    expect(result.current.loading).toBe(false);
  });

  it('preserves an ApiError (status kept)', async () => {
    mockApi.post.mockRejectedValueOnce(new ApiError('bad', 422));
    const { result } = renderHook(() => useApiMutation({ method: 'POST', componentName: 'F' }));

    await act(async () => {
      await result.current.mutate('/e', {}).catch(() => {});
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).status).toBe(422);
  });
});

describe('useApiMutation — reset & guard', () => {
  it('reset clears error and data', async () => {
    mockApi.post.mockResolvedValueOnce({ id: 9 });
    const { result } = renderHook(() => useApiMutation({ method: 'POST', componentName: 'F' }));
    await act(async () => {
      await result.current.mutate('/e', {});
    });
    expect(result.current.data).toEqual({ id: 9 });

    act(() => result.current.reset());
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('throws when options is missing', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() =>
      renderHook(() => useApiMutation(undefined as unknown as UseApiMutationOptions<unknown>))
    ).toThrow(/options is required/);
    spy.mockRestore();
  });
});
