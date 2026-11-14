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

vi.mock('@/hooks/useApplicationAccountQuery', () => ({
  useApplicationAccountQuery: () => ({ ...query, ownerId: 'one', refetch: vi.fn(async () => {}) }),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false }),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ refreshUser, user: { id: 'one' } }) }));

import {
  knownShortcutTokens,
  nextShortcutTokens,
  openableShortcutTokens,
  useSettingsShortcuts,
} from '@/hooks/useSettingsShortcuts';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import type { SettingsSectionToken } from '@/lib/settings-sections';

const OPEN: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  sandboxEgressEnabled: true,
  liveEnabled: true,
  avatarEnabled: true,
  radioEnabled: true,
  channelsEnabled: true,
  psycheEnabled: true,
  journalsEnabled: true,
  skillsEnabled: true,
  mcpEnabled: true,
  ragSpacesEnabled: true,
  imageGenerationEnabled: true,
  telephonyEnabled: true,
  hapticsSupported: true,
  debugUserAccess: true,
};

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

describe('openableShortcutTokens', () => {
  const pinned: SettingsSectionToken[] = ['theme', 'journals', 'admin-users', 'font'];

  it('keeps, in order, the pinned sections the account can open now', () => {
    expect(openableShortcutTokens(pinned, { ...OPEN, isSuperuser: true })).toEqual(pinned);
    expect(openableShortcutTokens(pinned, OPEN)).toEqual(['theme', 'journals', 'font']);
    expect(openableShortcutTokens(pinned, { ...OPEN, journalsEnabled: false })).toEqual([
      'theme',
      'font',
    ]);
  });

  it('keeps a section nothing here can rule out', () => {
    // `heartbeat` renders nothing until its own settings load: undecidable, so kept.
    expect(openableShortcutTokens(['heartbeat'], { ...OPEN, journalsEnabled: false })).toEqual([
      'heartbeat',
    ]);
  });
});

describe('nextShortcutTokens', () => {
  const stored: SettingsSectionToken[] = ['theme', 'journals', 'font'];
  const openable: SettingsSectionToken[] = ['theme', 'font'];

  it('adds a tick at the end and takes one away, keeping the stored order', () => {
    expect(nextShortcutTokens(stored, stored, 'language', 5)).toEqual([...stored, 'language']);
    expect(nextShortcutTokens(stored, stored, 'theme', 5)).toEqual(['journals', 'font']);
  });

  it('keeps a pin the account cannot open while there is room: it comes back with its capability', () => {
    expect(nextShortcutTokens(stored, openable, 'language', 5)).toEqual([
      'theme',
      'journals',
      'font',
      'language',
    ]);
    expect(nextShortcutTokens(stored, openable, 'theme', 5)).toEqual(['journals', 'font']);
  });

  it('lets a pin nobody can see give its place to the one the person just took', () => {
    // Three stored, two of them in the dock, a cap of three: the picker counts
    // two and offers a third. The list the API accepts holds what was chosen.
    expect(nextShortcutTokens(stored, openable, 'language', 3)).toEqual([
      'theme',
      'font',
      'language',
    ]);
  });

  it('gives up the hidden pins last first, and only as many as the cap asks', () => {
    const many: SettingsSectionToken[] = ['journals', 'theme', 'psyche', 'skills'];

    expect(nextShortcutTokens(many, ['theme'], 'font', 4)).toEqual([
      'journals',
      'theme',
      'psyche',
      'font',
    ]);
    expect(nextShortcutTokens(many, ['theme'], 'font', 3)).toEqual(['journals', 'theme', 'font']);
  });

  it('never gives up a pin the account can open: the picker blocks the box instead', () => {
    expect(nextShortcutTokens(['theme', 'font'], ['theme', 'font'], 'language', 2)).toEqual([
      'theme',
      'font',
      'language',
    ]);
  });

  it('applies no cap of its own while the server has not published one', () => {
    expect(nextShortcutTokens(stored, openable, 'language', 0)).toEqual([...stored, 'language']);
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
    mutate.mockImplementationOnce(async () => {
      query.data = { shortcuts: ['theme'], max_count: 5 };
      return query.data;
    });
    const { result, rerender } = renderHook(() => useSettingsShortcuts());

    let ok = false;
    await act(async () => {
      ok = await result.current.save(['theme']);
    });
    // The real owner query publishes its reply through React state.
    // This stub's externally held reply needs the corresponding rerender.
    rerender();

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
