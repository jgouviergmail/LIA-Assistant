'use client';

/**
 * useEffectsJournal — the user's own record of what LIA did (ADR-263).
 *
 * The reading rhythm (accumulation, reset on filter change, deduplication by
 * row id, exact server-side total) lives in `useRegisterJournal`, shared with
 * the consultation register: two copies would be two places for it to drift,
 * and a journal that behaves differently from its neighbour is two things to
 * learn instead of one.
 *
 * What stays here is what is specific to THIS register: its endpoint, and the
 * fact that its filter is an outcome.
 */

import {
  REGISTER_PAGE_SIZE,
  useRegisterJournal,
  type UseRegisterJournalResult,
} from '@/hooks/useRegisterJournal';
import type { EffectEntry, EffectStatus } from '@/types/effects';
import type { RegisterOrigin } from '@/types/register-origin';

/** Rows per request — one number, one reading rhythm. */
export const EFFECTS_PAGE_SIZE = REGISTER_PAGE_SIZE;

export type UseEffectsJournalResult = UseRegisterJournalResult<EffectEntry>;

/**
 * Read the action register.
 *
 * @param status - Restrict to one outcome. The filter travels to the SERVER,
 *   so `total` describes the list on screen and "load more" keeps working
 *   under it.
 * @param origin - Which authorships to read. Server-side for the same reason:
 *   a total computed over everything, shown above a filtered list, describes a
 *   set the reader cannot see.
 */
export function useEffectsJournal(
  status?: EffectStatus,
  origin: RegisterOrigin = 'all'
): UseEffectsJournalResult {
  return useRegisterJournal<EffectEntry>(
    (offset, limit) =>
      `/effects/journal?offset=${offset}&limit=${limit}` +
      (status ? `&status=${status}` : '') +
      (origin === 'all' ? '' : `&origin=${origin}`),
    // The reset key carries BOTH: changing tab must restart the accumulation,
    // or the initiative list would open on rows the person's own list left.
    `${origin}:${status ?? 'all'}`,
    'useEffectsJournal'
  );
}
