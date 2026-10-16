import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RequestConfig } from '@/lib/api-client';
import type { PsycheSettings, PsycheState } from '@/types/psyche';
import type {
  PersonalityListItem,
  PersonalityListResponse,
  UserPersonalityResponse,
  UserPersonalityUpdate,
} from '@/types/personality';

const {
  useAuth,
  get,
  patch,
  post,
  fetchPersonalities,
  fetchCurrentPersonality,
  updateCurrentPersonality,
} = vi.hoisted(() => ({
  useAuth: vi.fn(),
  fetchPersonalities: vi.fn<(signal?: AbortSignal) => Promise<PersonalityListResponse>>(),
  fetchCurrentPersonality: vi.fn<(signal?: AbortSignal) => Promise<UserPersonalityResponse>>(),
  updateCurrentPersonality:
    vi.fn<(body: UserPersonalityUpdate) => Promise<UserPersonalityResponse>>(),
  get: vi.fn<
    (url: string, config?: RequestConfig) => Promise<PsycheSettings | PsycheState | null>
  >(),
  patch: vi.fn<(url: string, data?: unknown, config?: RequestConfig) => Promise<PsycheSettings>>(),
  post: vi.fn<
    (
      url: string,
      data?: unknown,
      config?: RequestConfig
    ) => Promise<{ status: string; level: string }>
  >(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api/personality', () => ({
  fetchPersonalities,
  fetchCurrentPersonality,
  updateCurrentPersonality,
}));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch, post },
}));

import { publishApplicationResources } from '@/lib/application-resources';
import { usePsycheStore } from '@/stores/psycheStore';
import { usePersonalityStore } from '@/stores/personalityStore';
import { usePsyche } from '../usePsyche';

const preferences: PsycheSettings = {
  psyche_enabled: true,
  psyche_display_avatar: true,
  psyche_sensitivity: 50,
  psyche_stability: 50,
};

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReset();
  patch.mockReset();
  post.mockReset();
  fetchPersonalities.mockReset();
  fetchCurrentPersonality.mockReset();
  updateCurrentPersonality.mockReset();
  usePersonalityStore.getState().reset();
  fetchPersonalities.mockResolvedValue({ personalities: [CALM, DIRECT], total: 2 });
  fetchCurrentPersonality.mockResolvedValue({ personality: CALM, personality_id: CALM.id });
  updateCurrentPersonality.mockImplementation(async ({ personality_id }) => ({
    personality: personality_id === DIRECT.id ? DIRECT : CALM,
    personality_id,
  }));
  useAuth.mockReturnValue({ user: { id: 'one' } });
  usePsycheStore.getState().reset();
  get.mockImplementation((url: string) =>
    Promise.resolve(url === '/psyche/settings' ? preferences : null)
  );
});

describe('owned native psyche setting synchronization', () => {
  it('rereads state with settings after a native reset using only passive GET', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_enabled).toBe(true));
    get.mockClear();
    act(() => publishApplicationResources('one', new Set(['psyche'])));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/psyche/state?initialize=false', expect.anything())
    );
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
    usePsycheStore.getState().updateFromSSE({
      mood_label: 'playful',
      mood_color: '#22c55e',
      mood_pleasure: 0.8,
      mood_arousal: 0.4,
      mood_dominance: 0.6,
      active_emotion: 'joy',
      emotion_intensity: 0.9,
      relationship_stage: 'EXPLORATORY',
    });
    renderHook(() => usePsyche());
    expect(usePsycheStore.getState().moodLabel).toBe('playful');
    await act(async () => {
      await Promise.resolve();
    });
  });
  it('rereads source settings and synchronizes the avatar after a confirmed change', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings?.psyche_display_avatar).toBe(true));
    get.mockImplementation((url: string) =>
      Promise.resolve(
        url === '/psyche/settings' ? { ...preferences, psyche_display_avatar: false } : null
      )
    );
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
    await act(async () => {
      await result.current.updateSettings({ psyche_enabled: false });
    });
    expect(result.current.settings?.psyche_enabled).toBe(true);
    expect(usePsycheStore.getState().enabled).toBe(true);
  });
});

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  let reject: (error: Error) => void = () => {};
  const promise = new Promise<T>((accept, refuse) => {
    resolve = accept;
    reject = refuse;
  });
  return { promise, resolve, reject };
}

describe('psyche read status', () => {
  it('exposes an initial state read failure separately and recovers on retry', async () => {
    get.mockImplementation(url =>
      url === '/psyche/settings'
        ? Promise.resolve(preferences)
        : Promise.reject(new Error('state unavailable'))
    );
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.stateError?.message).toBe('state unavailable'));
    expect(result.current.settingsError).toBeNull();
    expect(result.current.error).toBe(result.current.stateError);
    expect(result.current.isLoading).toBe(false);
    get.mockImplementation(url => Promise.resolve(url === '/psyche/settings' ? preferences : null));
    await act(async () => {
      await result.current.refetchState();
    });
    expect(result.current.state).toBeNull();
    expect(result.current.stateError).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('exposes an initial settings failure instead of implying the feature is disabled', async () => {
    get.mockImplementation(url =>
      url === '/psyche/settings'
        ? Promise.reject(new Error('settings unavailable'))
        : Promise.resolve(null)
    );
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settingsError?.message).toBe('settings unavailable'));
    expect(result.current.stateError).toBeNull();
    expect(result.current.settings).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
  });

  it('retains loaded settings and distinguishes refresh from first load', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings).toEqual(preferences));
    const pending = deferred<PsycheSettings>();
    get.mockReturnValueOnce(pending.promise);
    let read: Promise<void> = Promise.resolve();
    act(() => {
      read = result.current.refetchSettings();
    });
    expect(result.current.settings).toEqual(preferences);
    expect(result.current.isRefreshing).toBe(true);
    expect(result.current.isLoading).toBe(false);
    await act(async () => {
      pending.resolve(preferences);
      await read;
    });
    expect(result.current.isRefreshing).toBe(false);
  });
});

describe('psyche mutation ownership and serialization', () => {
  it('allows one mutation at a time across settings and reset controls', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings).toEqual(preferences));
    const saved = deferred<PsycheSettings>();
    patch.mockReturnValueOnce(saved.promise);
    let first: ReturnType<typeof result.current.updateSettings> = Promise.resolve(null);
    act(() => {
      first = result.current.updateSettings({ psyche_sensitivity: 70 });
    });
    await act(async () => {
      expect(await result.current.updateSettings({ psyche_enabled: false })).toBeNull();
      expect(await result.current.resetPsyche('soft')).toBeNull();
    });
    expect(patch).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled();
    await act(async () => {
      saved.resolve(preferences);
      await first;
    });
    expect(result.current.isUpdatingSettings).toBe(false);
  });

  it('locks a pending reset and releases it after a failure for explicit retry', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings).toEqual(preferences));
    const reset = deferred<{ status: string; level: string }>();
    post.mockReturnValueOnce(reset.promise);
    let first: ReturnType<typeof result.current.resetPsyche> = Promise.resolve(null);
    act(() => {
      first = result.current.resetPsyche('soft');
    });
    await act(async () => {
      expect(await result.current.resetPsyche('full')).toBeNull();
    });
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => {
      reset.reject(new Error('retry reset'));
      await expect(first).rejects.toThrow('retry reset');
    });
    expect(result.current.isResetting).toBe(false);
    post.mockResolvedValueOnce({ status: 'reset', level: 'soft' });
    await act(async () => {
      await result.current.resetPsyche('soft');
    });
    expect(post).toHaveBeenCalledTimes(2);
  });

  it.each(['settings', 'reset'] as const)(
    'ignores an obsolete %s failure after switching account',
    async operation => {
      const { result, rerender } = renderHook(() => usePsyche());
      await waitFor(() => expect(result.current.settings).toEqual(preferences));
      const patchRequest = deferred<PsycheSettings>();
      const resetRequest = deferred<{ status: string; level: string }>();
      patch.mockReturnValueOnce(patchRequest.promise);
      post.mockReturnValueOnce(resetRequest.promise);
      let first:
        | ReturnType<typeof result.current.updateSettings>
        | ReturnType<typeof result.current.resetPsyche> = Promise.resolve(null);
      act(() => {
        first =
          operation === 'settings'
            ? result.current.updateSettings({ psyche_enabled: false })
            : result.current.resetPsyche('soft');
      });
      useAuth.mockReturnValue({ user: { id: 'two' } });
      rerender();
      await waitFor(() => expect(result.current.settings).toEqual(preferences));
      await act(async () => {
        if (operation === 'settings') patchRequest.reject(new Error('old failed'));
        else resetRequest.reject(new Error('old failed'));
        await expect(first).resolves.toBeNull();
      });
    }
  );

  it('does not carry a pending operation into B or let the old finally finish B reset', async () => {
    const { result, rerender } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings).toEqual(preferences));
    const saved = deferred<PsycheSettings>();
    const reset = deferred<{ status: string; level: string }>();
    patch.mockReturnValueOnce(saved.promise);
    post.mockReturnValueOnce(reset.promise);
    let old: ReturnType<typeof result.current.updateSettings> = Promise.resolve(null);
    act(() => {
      old = result.current.updateSettings({ psyche_enabled: false });
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.isUpdatingSettings).toBe(false);
    await waitFor(() => expect(result.current.settings).toEqual(preferences));
    let current: ReturnType<typeof result.current.resetPsyche> = Promise.resolve(null);
    act(() => {
      current = result.current.resetPsyche('soft');
    });
    await act(async () => {
      saved.resolve(preferences);
      await old;
    });
    expect(result.current.isResetting).toBe(true);
    await act(async () => {
      reset.resolve({ status: 'reset', level: 'soft' });
      await current;
    });
    expect(result.current.isResetting).toBe(false);
  });

  it('does not read or write without an authenticated account', async () => {
    useAuth.mockReturnValue({ user: null });
    const { result } = renderHook(() => usePsyche());
    await act(async () => {
      expect(await result.current.updateSettings({ psyche_enabled: true })).toBeNull();
      expect(await result.current.resetPsyche('soft')).toBeNull();
    });
    expect(get).not.toHaveBeenCalled();
    expect(patch).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
  });
});

describe('confirmed mutations with failed follow-up reads', () => {
  it('keeps the confirmed preferences when the observational reread fails', async () => {
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.settings).toEqual(preferences));
    const saved = { ...preferences, psyche_enabled: false, psyche_display_avatar: false };
    patch.mockResolvedValueOnce(saved);
    get.mockRejectedValueOnce(new Error('reread unavailable'));
    await act(async () => {
      await expect(
        result.current.updateSettings({ psyche_enabled: false, psyche_display_avatar: false })
      ).resolves.toEqual(saved);
    });
    expect(result.current.settings).toEqual(saved);
    expect(result.current.settingsError?.message).toBe('reread unavailable');
    expect(result.current.error).toBe(result.current.settingsError);
    expect(usePsycheStore.getState().enabled).toBe(false);
    expect(usePsycheStore.getState().displayAvatar).toBe(false);
  });

  it('returns the confirmed reset and clears old state when its observational reread fails', async () => {
    const oldState: PsycheState = {
      id: 'psyche-one',
      user_id: 'one',
      trait_openness: 0.5,
      trait_conscientiousness: 0.5,
      trait_extraversion: 0.5,
      trait_agreeableness: 0.5,
      trait_neuroticism: 0.5,
      mood_pleasure: 0.8,
      mood_arousal: 0.4,
      mood_dominance: 0.2,
      mood_label: 'playful',
      mood_color: '#22c55e',
      active_emotions: [],
      relationship_stage: 'EXPLORATORY',
      relationship_depth: 0.3,
      relationship_warmth_active: 0.5,
      relationship_trust: 0.4,
      relationship_interaction_count: 12,
      drive_curiosity: 0.5,
      drive_engagement: 0.5,
      self_efficacy: {},
      created_at: '2026-10-16T00:00:00Z',
      updated_at: '2026-10-16T00:30:00Z',
    };
    get.mockImplementation(url =>
      Promise.resolve(url === '/psyche/settings' ? preferences : oldState)
    );
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.state).toEqual(oldState));
    post.mockResolvedValueOnce({ status: 'reset', level: 'soft' });
    get.mockRejectedValueOnce(new Error('state reread unavailable'));
    await act(async () => {
      await expect(result.current.resetPsyche('soft')).resolves.toEqual({
        status: 'reset',
        level: 'soft',
      });
    });
    expect(result.current.state).toBeNull();
    expect(result.current.stateError?.message).toBe('state reread unavailable');
    expect(usePsycheStore.getState().fullState).toBeNull();
    expect(usePsycheStore.getState().moodLabel).toBe('neutral');
    expect(usePsycheStore.getState().enabled).toBe(true);
  });
});

const CALM: PersonalityListItem = {
  id: 'calm',
  code: 'calm',
  emoji: '🌊',
  is_default: true,
  title: 'Calm',
  description: 'Calm style',
};
const DIRECT: PersonalityListItem = {
  ...CALM,
  id: 'direct',
  code: 'direct',
  is_default: false,
  title: 'Direct',
  description: 'Direct style',
};

function psycheState(overrides: Partial<PsycheState> = {}): PsycheState {
  return {
    id: 'psyche-one',
    user_id: 'one',
    trait_openness: 0.5,
    trait_conscientiousness: 0.5,
    trait_extraversion: 0.5,
    trait_agreeableness: 0.5,
    trait_neuroticism: 0.5,
    mood_pleasure: 0.8,
    mood_arousal: 0.4,
    mood_dominance: 0.2,
    mood_label: 'playful',
    mood_color: '#22c55e',
    active_emotions: [],
    relationship_stage: 'EXPLORATORY',
    relationship_depth: 0.3,
    relationship_warmth_active: 0.5,
    relationship_trust: 0.4,
    relationship_interaction_count: 12,
    drive_curiosity: 0.5,
    drive_engagement: 0.5,
    self_efficacy: {},
    created_at: '2026-10-16T00:00:00Z',
    updated_at: '2026-10-16T00:30:00Z',
    ...overrides,
  };
}

const stateReads = () => get.mock.calls.filter(([url]) => url === '/psyche/state?initialize=false');

describe('confirmed personality changes refresh observed OCEAN traits', () => {
  it('rereads changed traits from the server after a shared personality selection', async () => {
    await usePersonalityStore.getState().load('one');
    const calm = psycheState();
    const direct = psycheState({ trait_openness: 0.8, trait_extraversion: 0.9 });
    get.mockImplementation(url =>
      Promise.resolve(
        url === '/psyche/settings'
          ? preferences
          : usePersonalityStore.getState().currentPersonalityId === DIRECT.id
            ? direct
            : calm
      )
    );
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.state).toEqual(calm));
    await act(async () => {
      await usePersonalityStore.getState().updatePersonality(DIRECT.id);
    });
    await waitFor(() => expect(result.current.state).toEqual(direct));
    expect(usePsycheStore.getState().fullState).toEqual(direct);
    expect(stateReads()).toHaveLength(2);
    expect(get.mock.calls.filter(([url]) => url === '/psyche/settings')).toHaveLength(1);
    expect(get.mock.calls.some(([url]) => url === '/psyche/state')).toBe(false);
  });

  it('refreshes traits when returning to the instance default', async () => {
    await usePersonalityStore.getState().load('one');
    await usePersonalityStore.getState().updatePersonality(DIRECT.id);
    const direct = psycheState({ trait_extraversion: 0.9 });
    const calm = psycheState({ trait_extraversion: 0.2 });
    get.mockImplementation(url =>
      Promise.resolve(
        url === '/psyche/settings'
          ? preferences
          : usePersonalityStore.getState().currentPersonalityId === DIRECT.id
            ? direct
            : calm
      )
    );
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.state).toEqual(direct));
    await act(async () => {
      await usePersonalityStore.getState().updatePersonality(null);
    });
    await waitFor(() => expect(result.current.state).toEqual(calm));
    expect(stateReads()).toHaveLength(2);
  });

  it('ignores an older in-flight observation after the confirmed style changes', async () => {
    await usePersonalityStore.getState().load('one');
    const calm = psycheState();
    const direct = psycheState({ trait_agreeableness: 0.9 });
    get.mockImplementation(url => Promise.resolve(url === '/psyche/settings' ? preferences : calm));
    const { result } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.state).toEqual(calm));
    const oldRead = deferred<PsycheState>();
    get.mockReturnValueOnce(oldRead.promise);
    let pending = Promise.resolve();
    act(() => {
      pending = result.current.refetchState().catch(() => {});
    });
    const oldSignal = stateReads()[1]?.[1]?.signal;
    get.mockImplementation(url =>
      Promise.resolve(url === '/psyche/settings' ? preferences : direct)
    );
    await act(async () => {
      await usePersonalityStore.getState().updatePersonality(DIRECT.id);
    });
    await waitFor(() => expect(result.current.state).toEqual(direct));
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => {
      oldRead.resolve(calm);
      await pending;
    });
    expect(result.current.state).toEqual(direct);
    expect(usePsycheStore.getState().fullState).toEqual(direct);
  });

  it('does not reread while a selection is pending, rejected, unchanged, or only relabelled', async () => {
    await usePersonalityStore.getState().load('one');
    const calm = psycheState();
    get.mockImplementation(url => Promise.resolve(url === '/psyche/settings' ? preferences : calm));
    const { result, rerender } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.state).toEqual(calm));
    await act(async () => {
      await usePersonalityStore.getState().updatePersonality(CALM.id);
    });
    expect(updateCurrentPersonality).not.toHaveBeenCalled();
    const selection = deferred<UserPersonalityResponse>();
    updateCurrentPersonality.mockReturnValueOnce(selection.promise);
    let pending = Promise.resolve();
    act(() => {
      pending = usePersonalityStore.getState().updatePersonality(DIRECT.id);
    });
    expect(usePersonalityStore.getState().updating).toBe(true);
    rerender();
    await act(async () => {
      await Promise.resolve();
    });
    expect(stateReads()).toHaveLength(1);
    await act(async () => {
      selection.reject(new Error('selection unavailable'));
      await expect(pending).rejects.toThrow('selection unavailable');
    });
    act(() =>
      usePersonalityStore.setState({
        currentPersonality: { ...CALM, title: 'New translated label' },
        personalities: [{ ...CALM, title: 'New translated label' }, DIRECT],
      })
    );
    rerender();
    await act(async () => {
      await Promise.resolve();
    });
    expect(stateReads()).toHaveLength(1);
    expect(result.current.state).toEqual(calm);
  });

  it('leaves a new account untouched when the previous account selection finishes late', async () => {
    await usePersonalityStore.getState().load('one');
    const one = psycheState();
    const two = psycheState({ user_id: 'two', trait_extraversion: 0.1 });
    get.mockImplementation(url =>
      Promise.resolve(
        url === '/psyche/settings'
          ? preferences
          : usePersonalityStore.getState().ownerId === 'two'
            ? two
            : one
      )
    );
    const { result, rerender } = renderHook(() => usePsyche());
    await waitFor(() => expect(result.current.state).toEqual(one));
    const selection = deferred<UserPersonalityResponse>();
    updateCurrentPersonality.mockReturnValueOnce(selection.promise);
    let pending = Promise.resolve();
    act(() => {
      pending = usePersonalityStore.getState().updatePersonality(DIRECT.id);
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    await act(async () => {
      await usePersonalityStore.getState().load('two');
      rerender();
    });
    await waitFor(() => expect(result.current.state).toEqual(two));
    const before = stateReads().length;
    await act(async () => {
      selection.resolve({ personality: DIRECT, personality_id: DIRECT.id });
      await pending;
    });
    expect(stateReads()).toHaveLength(before);
    expect(result.current.state).toEqual(two);
    expect(usePsycheStore.getState().fullState).toEqual(two);
  });
});
