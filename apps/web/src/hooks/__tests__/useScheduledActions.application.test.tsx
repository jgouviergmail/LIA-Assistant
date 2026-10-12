import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import { makeScheduledAction } from '@/__tests__/factories';

const { get, post, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post } };
});
import { useScheduledActions } from '../useScheduledActions';

const saved = {
  scheduled_actions: [makeScheduledAction({ id: 'routine', is_enabled: true })],
  total: 1,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith('/week') ? { actions: [], generated_at: '2026-10-07T12:00:00Z' } : saved
    )
  );
});

describe('routine state invalidation belongs to the authenticated account', () => {
  it('rereads both list and week only for its own committed changes', async () => {
    const { result } = renderHook(() => useScheduledActions());
    await waitFor(() => expect(result.current.actions).toHaveLength(1));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['routines'])));
    expect(get).not.toHaveBeenCalled();
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/week')
          ? { actions: [] }
          : {
              ...saved,
              scheduled_actions: [makeScheduledAction({ id: 'routine', is_enabled: false })],
            }
      )
    );
    act(() => publishApplicationResources('one', new Set(['routines'])));
    await waitFor(() => expect(result.current.actions[0]?.is_enabled).toBe(false));
    expect(get.mock.calls.map(call => call[0]).sort()).toEqual([
      '/scheduled-actions',
      '/scheduled-actions/week',
    ]);
  });

  it('hides the old account data while the new owner query is pending', async () => {
    const { result, rerender } = renderHook(() => useScheduledActions());
    await waitFor(() => expect(result.current.actions).toHaveLength(1));
    const retiredExecute = result.current.executeAction;
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.actions).toEqual([]);
    get.mockClear();
    act(() => publishApplicationResources('one', new Set(['routines'])));
    expect(get).not.toHaveBeenCalled();
    await act(async () => {
      await retiredExecute('routine');
    });
    expect(post).not.toHaveBeenCalled();
  });
});
