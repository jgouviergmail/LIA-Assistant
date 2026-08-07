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

/**
 * In-flight load, shared by every caller.
 *
 * Three components read this store and they mount together on the dashboard,
 * so without this they would each issue the same pair of requests. It lives
 * outside the store because it is plumbing, not state a component renders.
 */
let inFlight: Promise<void> | null = null;

export const usePersonalityStore = create<PersonalityStoreState>((set, get) => {
  const fetchBoth = async (): Promise<void> => {
    set({ loading: true, error: null });
    try {
      const [listResponse, currentResponse] = await Promise.all([
        fetchPersonalities(),
        fetchCurrentPersonality(),
      ]);
      set({
        personalities: listResponse.personalities,
        currentPersonality: currentResponse.personality,
        currentPersonalityId: currentResponse.personality_id,
      });
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to load personalities');
      set({ error });
      logger.error('personality_fetch_failed', error, { store: 'personalityStore' });
    } finally {
      set({ loading: false, hasLoaded: true });
    }
  };

  const run = (): Promise<void> => {
    // A rejected fetch is already turned into state by `fetchBoth`, so this
    // promise settles either way; the `finally` is what lets the next caller
    // start a fresh attempt rather than await a dead one.
    inFlight ??= fetchBoth().finally(() => {
      inFlight = null;
    });
    return inFlight;
  };

  return {
    ...INITIAL_STATE,

    load: async (ownerId) => {
      const state = get();
      if (state.ownerId !== ownerId) {
        // Another account, or the first load. Serving the previous user's
        // style to this one would be a leak, so the data goes before the
        // request that replaces it — the same reasoning as
        // `purgeSensitiveClientStorageOnAccountChange`.
        inFlight = null;
        set({ ...INITIAL_STATE, ownerId });
        await run();
        return;
      }
      // A settled attempt is enough — except a failed one, which a later
      // consumer deserves to see retried rather than inherit as an empty list.
      if (state.hasLoaded && !state.error) return;
      await run();
    },

    refetch: async () => {
      inFlight = null;
      await run();
    },

    updatePersonality: async (personalityId) => {
      set({ updating: true, error: null });
      try {
        const response = await updateCurrentPersonality({ personality_id: personalityId });
        set({
          currentPersonality: response.personality,
          currentPersonalityId: response.personality_id,
        });
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Failed to update personality');
        set({ error });
        logger.error('personality_update_failed', error, { store: 'personalityStore' });
        throw error;
      } finally {
        set({ updating: false });
      }
    },

    reset: () => {
      inFlight = null;
      set({ ...INITIAL_STATE });
    },
  };
});
