/**
 * useSettingsShortcuts — the pinned sections, read through this build's own
 * vocabulary and saved optimistically (ADR-277).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const query = vi.hoisted(() => ({
  data: null as { shortcuts: string[]; max_count: number } | null,
  loading: false,
  error: null as unknown,
}));
const mutate = vi.hoisted(() => vi.fn<(endpoint: string, body?: unknown) => Promise<unknown>>());
const refreshUser = vi.hoisted(() => vi.fn(async () => {}));

vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: () => query }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false }),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ refreshUser }) }));

import { knownShortcutTokens, useSettingsShortcuts } from '@/hooks/useSettingsShortcuts';

beforeEach(() => {
  vi.clearAllMocks();
  query.data = { shortcuts: ['theme', 'font'], max_count: 5 };
  mutate.mockResolvedValue({});
});

describe('knownShortcutTokens', () => {
  it('keeps the known tokens in stored order, each once', () => {
    expect(knownShortcutTokens(['font', 'theme', 'font'])).toEqual(['font', 'theme']);
  });

  it('drops a token this build no longer declares', () => {
    // A section renamed since it was pinned is not a dead link.
    expect(knownShortcutTokens(['theme', 'gone-section'])).toEqual(['theme']);
  });

  it('drops the picker itself', () => {
    expect(knownShortcutTokens(['my-shortcuts', 'theme'])).toEqual(['theme']);
  });

  it('reads nothing as nothing', () => {
    expect(knownShortcutTokens(null)).toEqual([]);
    expect(knownShortcutTokens(undefined)).toEqual([]);
  });
});

describe('useSettingsShortcuts', () => {
  it('exposes the server list, filtered, and the runtime cap', () => {
    query.data = { shortcuts: ['theme', 'gone-section'], max_count: 5 };

    const { result } = renderHook(() => useSettingsShortcuts());

    expect(result.current.shortcuts).toEqual(['theme']);
    expect(result.current.maxCount).toBe(5);
  });

  it('saves optimistically, then refreshes the signed-in user so every screen follows', async () => {
    const { result } = renderHook(() => useSettingsShortcuts());

    let ok = false;
    await act(async () => {
      ok = await result.current.save(['theme']);
    });

    expect(ok).toBe(true);
    expect(mutate).toHaveBeenCalledWith('/users/me/settings-shortcuts', { shortcuts: ['theme'] });
    expect(refreshUser).toHaveBeenCalledTimes(1);
    expect(result.current.shortcuts).toEqual(['theme']);
  });

  it('rolls back a refused save and refreshes nobody', async () => {
    mutate.mockRejectedValueOnce(new Error('400'));
    const { result } = renderHook(() => useSettingsShortcuts());

    let ok = true;
    await act(async () => {
      ok = await result.current.save(['theme']);
    });

    expect(ok).toBe(false);
    expect(result.current.shortcuts).toEqual(['theme', 'font']);
    expect(refreshUser).not.toHaveBeenCalled();
  });
});
