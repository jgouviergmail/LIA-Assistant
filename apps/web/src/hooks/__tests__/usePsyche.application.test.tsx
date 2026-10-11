import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useAuth, get, patch } = vi.hoisted(() => ({ useAuth: vi.fn(), get: vi.fn(), patch: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch },
}));

import { publishApplicationResources } from '@/lib/application-resources';
import { usePsycheStore } from '@/stores/psycheStore';
import { usePsyche } from '../usePsyche';

const preferences = { psyche_enabled: true, psyche_display_avatar: true, psyche_sensitivity: 50, psyche_stability: 50 };

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  patch.mockReset();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  usePsycheStore.getState().reset();
  get.mockImplementation((url: string) => Promise.resolve(url === '/psyche/settings' ? preferences : null));
});

describe('owned native psyche setting synchronization', () => {
  it('rereads state with settings after a native reset using only passive GET', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_enabled).toBe(true));
    get.mockClear();
    act(() => publishApplicationResources('one', new Set(['psyche'])));
    await waitFor(() => expect(get).toHaveBeenCalledWith('/psyche/state?initialize=false', expect.anything()));
    expect(get.mock.calls.some(([url]) => url === '/psyche/state')).toBe(false);
  });

  it('clears an authoritative absent state without clearing the current personal preferences', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_enabled).toBe(true));
    usePsycheStore.setState({ moodLabel: 'playful', enabled: true, displayAvatar: false });
    act(() => publishApplicationResources('one', new Set(['psyche'])));
    await waitFor(() => expect(usePsycheStore.getState().moodLabel).toBe('neutral'));
    expect(usePsycheStore.getState().enabled).toBe(true);
  });
  it('preserves current account live mood when another panel mounts', async () => {
    const first = renderHook(() => usePsyche());
    await waitFor(() => expect(first.result.current.settings?.psyche_enabled).toBe(true));
    usePsycheStore.getState().updateFromSSE({ mood_label: 'playful', mood_color: '#22c55e', mood_pleasure: 0.8, mood_arousal: 0.4, mood_dominance: 0.6, active_emotion: 'joy', emotion_intensity: 0.9, relationship_stage: 'EXPLORATORY' });
    renderHook(() => usePsyche());
    expect(usePsycheStore.getState().moodLabel).toBe('playful');
  });
  it('rereads source settings and synchronizes the avatar after a confirmed change', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_display_avatar).toBe(true));
    get.mockImplementation((url: string) => Promise.resolve(url === '/psyche/settings' ? { ...preferences, psyche_display_avatar: false } : null));
    act(() => publishApplicationResources('one', new Set(['psyche'])));
    await waitFor(() => expect(result.current.settings?.psyche_display_avatar).toBe(false));
    expect(usePsycheStore.getState().displayAvatar).toBe(false);
  });

  it('hides previous account settings and refuses its obsolete write callback', async () => {
    const { result, rerender } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_enabled).toBe(true));
    const obsolete = result.current.updateSettings;
    get.mockImplementation(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.settings).toBeUndefined();
    await act(async () => expect(await obsolete({ psyche_enabled: false })).toBeNull());
    expect(patch).not.toHaveBeenCalled();
    expect(usePsycheStore.getState().enabled).toBe(false);
  });

  it('lets the authoritative reread win over a mutation request that is already superseded', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_enabled).toBe(true));
    patch.mockResolvedValue({ ...preferences, psyche_enabled: false });
    await act(async () => { await result.current.updateSettings({ psyche_enabled: false }); });
    expect(result.current.settings?.psyche_enabled).toBe(true);
    expect(usePsycheStore.getState().enabled).toBe(true);
  });
});
