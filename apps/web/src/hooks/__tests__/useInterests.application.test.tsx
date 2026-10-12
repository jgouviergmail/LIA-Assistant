import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, post, patch, remove, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post, patch, delete: remove } };
});
import { useInterests } from '../useInterests';

const saved = {
  interests: [{ id: 'interest', topic: 'Owned topic', category: 'science', status: 'active' }],
  total: 1,
  active_count: 1,
  blocked_count: 0,
  dormant_count: 0,
};
const preferences = {
  interests_enabled: true,
  interests_notify_start_hour: 8,
  interests_notify_end_hour: 22,
  interests_notify_min_per_day: 1,
  interests_notify_max_per_day: 5,
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((endpoint: string) =>
    Promise.resolve(
      endpoint === '/interests/categories'
        ? { categories: [] }
        : endpoint === '/interests/settings'
          ? preferences
          : saved
    )
  );
});

describe('interest management is current and account scoped', () => {
  it('rereads confirmed settings for their owner while retaining loaded data and filters', async () => {
    const { result } = renderHook(() => useInterests());
    await waitFor(() => expect(result.current.settings?.interests_enabled).toBe(true));
    act(() => result.current.setCategoryFilter('science'));
    get.mockClear();
    act(() => publishApplicationResources('foreign', new Set(['interests'])));
    expect(get).not.toHaveBeenCalled();
    get.mockImplementation((endpoint: string) =>
      Promise.resolve(
        endpoint === '/interests/settings' ? { ...preferences, interests_enabled: false } : saved
      )
    );
    act(() => publishApplicationResources('one', new Set(['interests'])));
    await waitFor(() => expect(result.current.settings?.interests_enabled).toBe(false));
    expect(result.current.categoryFilter).toBe('science');
    expect(result.current.interests).toHaveLength(1);
    expect(get).toHaveBeenCalledWith('/interests', expect.anything());
    expect(get).toHaveBeenCalledWith('/interests/settings', expect.anything());
  });

  it('hides old-account data and refuses every retired mutation callback', async () => {
    const { result, rerender } = renderHook(() => useInterests());
    await waitFor(() => expect(result.current.settings).toBeDefined());
    const retired = result.current;
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.allInterests).toEqual([]);
    expect(result.current.settings).toBeUndefined();
    await act(async () => {
      await retired.createInterest({ topic: 'Old', category: 'other' });
      await retired.updateInterest('interest', { topic: 'Old' });
      await retired.deleteInterest('interest');
      await retired.deleteAllInterests();
      await retired.submitFeedback('interest', 'block');
      await retired.reactivateInterest('interest');
      await retired.updateSettings({ interests_enabled: false });
    });
    expect(post).not.toHaveBeenCalled();
    expect(patch).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });
});
