/**
 * The personality is one preference, so it must be one piece of state.
 *
 * Reported 2026-08-07, on the production app and on the public demonstrator:
 * changing the style in Settings left the header showing the previous one
 * until the page was reloaded by hand. The cause was not a stale cache but an
 * absent one — `usePersonality` held its data in `useState`, so every consumer
 * owned a private copy. Three components call it (the header selector, the
 * settings panel, the starter checklist), which also meant three identical
 * round-trips on every dashboard mount.
 *
 * The defect is symmetric, and the report only saw one half of it: changing
 * the style from the HEADER left the settings panel stale in exactly the same
 * way. Both directions are covered below.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PersonalityListItem } from '@/types/personality';

const fetchPersonalities = vi.fn();
const fetchCurrentPersonality = vi.fn();
const updateCurrentPersonality = vi.fn();

vi.mock('@/lib/api/personality', () => ({
  fetchPersonalities: () => fetchPersonalities(),
  fetchCurrentPersonality: () => fetchCurrentPersonality(),
  updateCurrentPersonality: (body: unknown) => updateCurrentPersonality(body),
}));

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { usePersonalityStore } from '@/stores/personalityStore';

const CALM: PersonalityListItem = {
  id: 'calm-id',
  code: 'calm',
  emoji: '🌊',
  is_default: true,
  title: 'Posé',
  description: 'Répond calmement',
};

const SHARP: PersonalityListItem = {
  id: 'sharp-id',
  code: 'sharp',
  emoji: '⚡',
  is_default: false,
  title: 'Incisif',
  description: 'Va droit au but',
};

/** The state as a component reading the store would see it. */
const snapshot = () => {
  const { currentPersonality, currentPersonalityId, personalities, loading, updating, error } =
    usePersonalityStore.getState();
  return { currentPersonality, currentPersonalityId, personalities, loading, updating, error };
};

beforeEach(() => {
  vi.clearAllMocks();
  usePersonalityStore.getState().reset();
  fetchPersonalities.mockResolvedValue({ personalities: [CALM, SHARP], count: 2 });
  fetchCurrentPersonality.mockResolvedValue({ personality: CALM, personality_id: CALM.id });
  updateCurrentPersonality.mockImplementation(async ({ personality_id }: { personality_id: string | null }) => {
    const chosen = [CALM, SHARP].find((p) => p.id === personality_id) ?? null;
    return { personality: chosen, personality_id: chosen?.id ?? null };
  });
});

describe('the shared personality state', () => {
  it('serves every reader the value the last writer stored', async () => {
    await usePersonalityStore.getState().load('user-1');
    expect(snapshot().currentPersonality).toEqual(CALM);

    // The settings panel writes...
    await usePersonalityStore.getState().updatePersonality(SHARP.id);

    // ...and the header, reading the same state, is already up to date.
    expect(snapshot().currentPersonality).toEqual(SHARP);
    expect(snapshot().currentPersonalityId).toBe(SHARP.id);
  });

  it('carries a change made from the header back to the settings panel', async () => {
    await usePersonalityStore.getState().load('user-1');

    await usePersonalityStore.getState().updatePersonality(SHARP.id);
    await usePersonalityStore.getState().updatePersonality(CALM.id);

    expect(snapshot().currentPersonality).toEqual(CALM);
  });

  it('accepts clearing the preference back to the default', async () => {
    await usePersonalityStore.getState().load('user-1');
    await usePersonalityStore.getState().updatePersonality(SHARP.id);

    await usePersonalityStore.getState().updatePersonality(null);

    expect(snapshot().currentPersonality).toBeNull();
    expect(snapshot().currentPersonalityId).toBeNull();
  });
});

describe('loading', () => {
  it('fetches once however many components ask at the same time', async () => {
    // Three consumers mount together on the dashboard. Before this store they
    // produced three identical pairs of requests.
    await Promise.all([
      usePersonalityStore.getState().load('user-1'),
      usePersonalityStore.getState().load('user-1'),
      usePersonalityStore.getState().load('user-1'),
    ]);

    expect(fetchPersonalities).toHaveBeenCalledTimes(1);
    expect(fetchCurrentPersonality).toHaveBeenCalledTimes(1);
  });

  it('does not fetch again for a consumer mounting later', async () => {
    await usePersonalityStore.getState().load('user-1');

    await usePersonalityStore.getState().load('user-1');

    expect(fetchPersonalities).toHaveBeenCalledTimes(1);
  });

  it('refetches when asked explicitly, so an external change can be picked up', async () => {
    await usePersonalityStore.getState().load('user-1');

    await usePersonalityStore.getState().refetch();

    expect(fetchPersonalities).toHaveBeenCalledTimes(2);
  });

  it('reports a failed load without leaving the reader waiting forever', async () => {
    fetchPersonalities.mockRejectedValue(new Error('network down'));

    await usePersonalityStore.getState().load('user-1');

    expect(snapshot().loading).toBe(false);
    expect(snapshot().error).toBeInstanceOf(Error);
  });

  it('lets a later attempt succeed after a failure', async () => {
    fetchPersonalities.mockRejectedValueOnce(new Error('network down'));
    await usePersonalityStore.getState().load('user-1');

    await usePersonalityStore.getState().refetch();

    expect(snapshot().error).toBeNull();
    expect(snapshot().personalities).toHaveLength(2);
  });
});

describe('the state belongs to one account', () => {
  it('drops the previous account data when another user loads', async () => {
    await usePersonalityStore.getState().load('user-1');
    await usePersonalityStore.getState().updatePersonality(SHARP.id);
    fetchCurrentPersonality.mockResolvedValue({ personality: null, personality_id: null });

    await usePersonalityStore.getState().load('user-2');

    expect(snapshot().currentPersonality).toBeNull();
    expect(fetchCurrentPersonality).toHaveBeenCalledTimes(2);
  });

  it('keeps serving the same account without refetching', async () => {
    await usePersonalityStore.getState().load('user-1');

    await usePersonalityStore.getState().load('user-1');

    expect(fetchCurrentPersonality).toHaveBeenCalledTimes(1);
  });

  it('reset clears everything, so a logout leaves nothing behind', async () => {
    await usePersonalityStore.getState().load('user-1');

    usePersonalityStore.getState().reset();

    expect(snapshot().currentPersonality).toBeNull();
    expect(snapshot().personalities).toEqual([]);
    expect(snapshot().error).toBeNull();
  });
});

describe('a failed update', () => {
  it('rethrows so the caller can tell the user', async () => {
    await usePersonalityStore.getState().load('user-1');
    updateCurrentPersonality.mockRejectedValue(new Error('refused'));

    await expect(usePersonalityStore.getState().updatePersonality(SHARP.id)).rejects.toThrow(
      'refused'
    );
  });

  it('leaves the previous choice in place rather than a half-applied one', async () => {
    await usePersonalityStore.getState().load('user-1');
    updateCurrentPersonality.mockRejectedValue(new Error('refused'));

    await expect(usePersonalityStore.getState().updatePersonality(SHARP.id)).rejects.toThrow();

    expect(snapshot().currentPersonality).toEqual(CALM);
    expect(snapshot().updating).toBe(false);
  });
});

describe('a rejection that is not an Error', () => {
  // `api-client` normally rejects with `ApiError`, but nothing in the type
  // system guarantees it: a network layer, an interceptor or a stray `throw`
  // can produce a string. The store must still hand its readers something
  // with a `message`, or the UI renders "[object Object]" at them.
  it('is still reported as an Error when loading', async () => {
    fetchPersonalities.mockRejectedValue('connexion interrompue');

    await usePersonalityStore.getState().load('user-1');

    expect(snapshot().error).toBeInstanceOf(Error);
    expect(snapshot().error?.message).toBe('Failed to load personalities');
  });

  it('is still reported as an Error when updating', async () => {
    await usePersonalityStore.getState().load('user-1');
    updateCurrentPersonality.mockRejectedValue('refus du serveur');

    await expect(usePersonalityStore.getState().updatePersonality(SHARP.id)).rejects.toThrow(
      'Failed to update personality'
    );

    expect(snapshot().error).toBeInstanceOf(Error);
  });
});
