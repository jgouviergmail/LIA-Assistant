/**
 * Zustand store for the user's conversational style (personality).
 *
 * One preference, one piece of state. It used to live in `useState` inside
 * `usePersonality`, which gave every consumer a private copy: changing the
 * style in Settings left the header showing the previous one until the page
 * was reloaded by hand (reported 2026-08-07, on production and on the public
 * demonstrator). The defect was symmetric — a change made from the header
 * left the settings panel stale in the same way.
 *
 * Consumed by:
 * - PersonalitySelector (dashboard header) — reads AND writes
 * - PersonalitySettings (settings page) — reads AND writes
 * - StarterChecklistCard (dashboard) — reads
 *
 * No persistence: the server is the source of truth, and a cached preference
 * would outlive the account it belongs to. For the same reason the state is
 * stamped with its owner — see `load`.
 *
 * Created: 2026-08-07
 */

import { create } from 'zustand';

import {
  fetchCurrentPersonality,
  fetchPersonalities,
  updateCurrentPersonality,
} from '@/lib/api/personality';
import { logger } from '@/lib/logger';
import type { PersonalityListItem } from '@/types/personality';

interface PersonalityStoreState {
  /** Account this state belongs to; `null` before the first load. */
  ownerId: string | null;
  /** Styles offered by the instance. */
  personalities: PersonalityListItem[];
  /** The user's current style (`null` = the instance default). */
  currentPersonality: PersonalityListItem | null;
  /** Identifier of the current style, mirroring the server's own field. */
  currentPersonalityId: string | null;
  loading: boolean;
  /**
   * Whether a first attempt has settled, successfully or not.
   *
   * Distinct from `loading`: a consumer mounting before anything was requested
   * must show its waiting state, not an empty list. `loading` alone is false
   * at that instant, which would flash "no styles" before the first paint.
   */
  hasLoaded: boolean;
  updating: boolean;
  error: Error | null;

  /** Load once for `ownerId`; refetches only when the account changes. */
  load: (ownerId: string | null) => Promise<void>;
  /** Fetch again unconditionally, for a caller that knows the data moved. */
  refetch: () => Promise<void>;
  /** Persist a new style; every reader sees it as soon as the server agrees. */
  updatePersonality: (personalityId: string | null) => Promise<void>;
  /** Drop everything — logout, or an account we no longer serve. */
  reset: () => void;
}

const INITIAL_STATE = {
  ownerId: null,
  personalities: [],
  currentPersonality: null,
  currentPersonalityId: null,
  loading: false,
  hasLoaded: false,
  updating: false,
  error: null,
} satisfies Omit<PersonalityStoreState, 'load' | 'refetch' | 'updatePersonality' | 'reset'>;

interface ReadRequest {
  generation: number;
  controller: AbortController;
  promise: Promise<void>;
}

interface MutationRequest {
  generation: number;
  promise: Promise<void>;
}

export const usePersonalityStore = create<PersonalityStoreState>((set, get) => {
  // Object identity orders requests; the generation also invalidates A → B → A.
  let generation = 0;
  let activeRead: ReadRequest | null = null;
  let activeMutation: MutationRequest | null = null;

  const cancelRead = () => {
    activeRead?.controller.abort();
    activeRead = null;
  };

  const resetOwner = (ownerId: string | null) => {
    generation += 1;
    cancelRead();
    activeMutation = null;
    set({ ...INITIAL_STATE, ownerId });
  };

  const fetchBoth = async (request: ReadRequest): Promise<void> => {
    const isCurrent = () => activeRead === request && generation === request.generation;
    set({ loading: true, error: null });
    try {
      const [listResponse, currentResponse] = await Promise.all([
        fetchPersonalities(request.controller.signal),
        fetchCurrentPersonality(request.controller.signal),
      ]);
      if (!isCurrent()) return;
      set({
        personalities: listResponse.personalities,
        currentPersonality: currentResponse.personality,
        currentPersonalityId: currentResponse.personality_id,
      });
    } catch (err) {
      if (!isCurrent()) return;
      request.controller.abort();
      const error = err instanceof Error ? err : new Error('Failed to load personalities');
      set({ error });
      logger.error('personality_fetch_failed', error, { store: 'personalityStore' });
    } finally {
      if (isCurrent()) {
        activeRead = null;
        set({ loading: false, hasLoaded: true });
      }
    }
  };

  const run = (): Promise<void> => {
    if (activeRead) return activeRead.promise;
    if (!get().ownerId) return Promise.resolve();
    const request: ReadRequest = {
      generation,
      controller: new AbortController(),
      promise: Promise.resolve(),
    };
    activeRead = request;
    request.promise = fetchBoth(request);
    return request.promise;
  };

  const persist = async (request: MutationRequest, personalityId: string | null) => {
    const isCurrent = () => activeMutation === request && generation === request.generation;
    try {
      const response = await updateCurrentPersonality({ personality_id: personalityId });
      if (!isCurrent()) return;
      set({
        currentPersonality: response.personality,
        currentPersonalityId: response.personality_id,
      });
    } catch (err) {
      if (!isCurrent()) return;
      const error = err instanceof Error ? err : new Error('Failed to update personality');
      set({ error });
      logger.error('personality_update_failed', error, { store: 'personalityStore' });
      throw error;
    } finally {
      if (isCurrent()) {
        activeMutation = null;
        set({ updating: false });
      }
    }
  };

  return {
    ...INITIAL_STATE,

    load: async ownerId => {
      if (get().ownerId !== ownerId) resetOwner(ownerId);
      const state = get();
      if (!ownerId || (state.hasLoaded && !state.error)) return;
      await run();
    },

    refetch: async () => {
      const ownerGeneration = generation;
      const mutation = activeMutation;
      // An admin catalogue refresh must read the confirmed preference, not
      // race its save. Several readers waiting on that save share one read.
      if (mutation) await mutation.promise.catch(() => {});
      if (ownerGeneration !== generation || !get().ownerId) return;
      if (!mutation) cancelRead();
      await run();
    },

    updatePersonality: async personalityId => {
      const state = get();
      if (
        !state.ownerId ||
        !state.hasLoaded ||
        state.updating ||
        personalityId === state.currentPersonalityId ||
        personalityId === state.currentPersonality?.id
      )
        return;
      cancelRead();
      const request: MutationRequest = { generation, promise: Promise.resolve() };
      activeMutation = request;
      set({ updating: true, loading: false, error: null });
      request.promise = persist(request, personalityId);
      await request.promise;
    },

    reset: () => resetOwner(null),
  };
});
