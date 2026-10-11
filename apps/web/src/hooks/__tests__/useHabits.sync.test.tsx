import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth, get, patch, remove } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch, delete: remove },
}));
import { publishApplicationResources } from '@/lib/application-resources';
import { useHabits } from '../useHabits';

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  patch.mockReset();
  remove.mockReset();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue({ habits_enabled: true, habits: [{ id: 'private-one' }] });
});

describe('owned habit management synchronization', () => {
  it.each([
    [{ deleted_habits: 1, profile_deleted: true, advisory_cleanup_confirmed: true }, 'complete'],
    [{ deleted_habits: 1, profile_deleted: true, advisory_cleanup_confirmed: false }, 'partial'],
    [{ deleted_habits: 1, profile_deleted: true }, 'partial'],
    [{ profile_deleted: 'false' }, 'failed'],
  ] as const)('reports the actual forgetting outcome without hiding partial cleanup', async (response, expected) => {
    const { result } = renderHook(() => useHabits());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    remove.mockResolvedValue(response);
    await act(async () => expect(await result.current.removeAll()).toBe(expected));
    expect(remove).toHaveBeenCalledTimes(1);
  });
  it('rereads the source after a confirmed native learning preference change', async () => {
    const { result } = renderHook(() => useHabits());
    await waitFor(() => expect(result.current.overview?.habits_enabled).toBe(true));
    get.mockResolvedValue({ habits_enabled: false, habits: [{ id: 'private-one' }] });
    act(() => publishApplicationResources('one', new Set(['habits'])));
    await waitFor(() => expect(result.current.overview?.habits_enabled).toBe(false));
  });

  it('hides previous account habits and refuses its obsolete mutation callback', async () => {
    const { result, rerender } = renderHook(() => useHabits());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    const obsolete = result.current.setEnabled;
    get.mockImplementationOnce(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.overview).toBeNull();
    await act(async () => {
      expect(await obsolete(false)).toBe(false);
    });
    expect(patch).not.toHaveBeenCalled();
  });

  it.each(['paused', 'blocked', 'deleted'])('rereads a confirmed %s record change', async status => {
    const { result } = renderHook(() => useHabits());
    await waitFor(() => expect(result.current.overview?.habits).toHaveLength(1));
    get.mockResolvedValue({ habits_enabled: true, habits: status === 'deleted' ? [] : [{ id: 'private-one', status }] });
    act(() => publishApplicationResources('one', new Set(['habits'])));
    await waitFor(() => {
      if (status === 'deleted') expect(result.current.overview?.habits).toEqual([]);
      else expect(result.current.overview?.habits[0].status).toBe(status);
    });
  });
});
