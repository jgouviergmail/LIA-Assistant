/**
 * Builders for the return values of the data hooks (`useApiQuery` /
 * `useApiMutation`), so component tests can mock them without repeating the full
 * result shape in every file.
 *
 * The canonical pattern (see `GUIDE_TESTING.md` → Tests Frontend) is to mock the
 * hook module with `vi.mock` and route each call through one of these builders:
 *
 * ```ts
 * import { vi } from 'vitest';
 * import { dataQuery, loadingQuery, errorQuery } from '@/__tests__/api-mocks';
 *
 * const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
 * vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
 *
 * useApiQuery.mockReturnValue(dataQuery({ items: [] }));   // success
 * useApiQuery.mockReturnValue(loadingQuery());             // spinner branch
 * useApiQuery.mockReturnValue(errorQuery('boom'));         // error branch
 * ```
 *
 * When a component calls `useApiQuery` for several endpoints, route by the first
 * argument inside `mockImplementation` (see `useSpaces.test.ts`).
 */

import { vi } from 'vitest';

import type { UseApiQueryResult } from '@/hooks/useApiQuery';
import type { UseApiMutationResult } from '@/hooks/useApiMutation';

/** A `useApiQuery` result with idle defaults; override any field. */
export function queryResult<T>(over: Partial<UseApiQueryResult<T>> = {}): UseApiQueryResult<T> {
  return {
    data: undefined,
    loading: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    setData: vi.fn(),
    ...over,
  };
}

/** A settled `useApiQuery` result carrying `data`. */
export function dataQuery<T>(data: T, over: Partial<UseApiQueryResult<T>> = {}): UseApiQueryResult<T> {
  return queryResult<T>({ data, ...over });
}

/** A `useApiQuery` result in its loading state. */
export function loadingQuery<T>(over: Partial<UseApiQueryResult<T>> = {}): UseApiQueryResult<T> {
  return queryResult<T>({ loading: true, ...over });
}

/** A `useApiQuery` result carrying an `Error`. */
export function errorQuery<T>(
  message = 'test error',
  over: Partial<UseApiQueryResult<T>> = {}
): UseApiQueryResult<T> {
  return queryResult<T>({ error: new Error(message), ...over });
}

/**
 * A `useApiMutation` result with idle defaults. `mutate` resolves `undefined`
 * unless overridden; pass `{ mutate: vi.fn().mockResolvedValue(payload) }` to
 * simulate a successful response, or `{ mutate: vi.fn().mockRejectedValue(err) }`
 * to drive the error path.
 */
export function mutationResult<TData = unknown, TResponse = unknown>(
  over: Partial<UseApiMutationResult<TData, TResponse>> = {}
): UseApiMutationResult<TData, TResponse> {
  return {
    mutate: vi.fn().mockResolvedValue(undefined),
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
    ...over,
  };
}
