'use client';

/**
 * useWorkboardCategories — what ADMINISTERING the categories needs (ADR-276).
 *
 * One read, `GET /workboard/categories`: every category on the reader's board
 * with its exact ticket count, and the caps the instance enforces (ADR-184).
 * The list also holds the categories of the tickets the reader merely HOLDS
 * for somebody else — theirs to read, never to change (owner arbitration,
 * 2026-11-11) — so what this hook hands out is the reader's OWN, in their
 * order: what they manage.
 *
 * It is the manager's hook and nothing else's: the board itself names every
 * category in sight through its own lanes (`lib/workboard/lanes.ts`), so
 * nothing that DRAWS reads this list.
 *
 * The three writes answer like the board's own verbs: `{ok, errorCode}` with
 * the backend's stable `workboard_*` code, so no caller translates a sentence
 * or forgets a `catch`. A write that succeeded re-reads the list BEFORE it
 * answers; one that was refused leaves it alone.
 */

import { useCallback, useMemo } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import { useAuth } from '@/hooks/useAuth';
import { workboardErrorCode, type WriteOutcome } from '@/hooks/useWorkboard';
import { workboardApi } from '@/lib/workboard/api';
import type {
  CategoryCreateBody,
  CategoryList,
  CategoryRow,
  CategoryUpdateBody,
} from '@/types/workboard';

/** What a deletion answers: the outcome, and what it did to the tickets. */
export interface CategoryRemoval extends WriteOutcome {
  /** Tickets sent back to the unfiled lane; absent when the deletion was refused. */
  released?: number;
}

export interface UseWorkboardCategoriesResult {
  /** The reader's own categories, in their order; empty until the first answer. */
  own: readonly CategoryRow[];
  /** Categories an account may define; undefined until the first answer. */
  maxCategories: number | undefined;
  /** Longest name accepted; undefined until the first answer. */
  nameMaxChars: number | undefined;
  /** True only before the first answer — never on a re-read. */
  firstLoad: boolean;
  error: boolean;
  create: (body: CategoryCreateBody) => Promise<WriteOutcome>;
  update: (id: string, body: CategoryUpdateBody) => Promise<WriteOutcome>;
  remove: (id: string) => Promise<CategoryRemoval>;
}

const NONE: readonly CategoryRow[] = [];

/**
 * @param enabled - Whether to read at all: the list is asked for only while
 *   the dialog that shows it is open.
 */
export function useWorkboardCategories(enabled: boolean): UseWorkboardCategoriesResult {
  const { user } = useAuth();
  const meId = user?.id;
  const { data, error, refetch } = useApiQuery<CategoryList>('/workboard/categories', {
    componentName: 'useWorkboardCategories',
    enabled,
  });

  const categories = data?.categories ?? NONE;
  const own = useMemo(
    () => categories.filter(row => row.owner_user_id === meId),
    [categories, meId]
  );

  /** Run one write: re-read on success, answer the code on refusal. */
  const write = useCallback(
    async <T>(call: () => Promise<T>): Promise<{ outcome: WriteOutcome; value: T | undefined }> => {
      try {
        const value = await call();
        await refetch();
        return { outcome: { ok: true, errorCode: null }, value };
      } catch (caught) {
        return { outcome: { ok: false, errorCode: workboardErrorCode(caught) }, value: undefined };
      }
    },
    [refetch]
  );

  const create = useCallback(
    async (body: CategoryCreateBody) =>
      (await write(() => workboardApi.createCategory(body))).outcome,
    [write]
  );
  const update = useCallback(
    async (id: string, body: CategoryUpdateBody) =>
      (await write(() => workboardApi.updateCategory(id, body))).outcome,
    [write]
  );
  const remove = useCallback(
    async (id: string): Promise<CategoryRemoval> => {
      const { outcome, value } = await write(() => workboardApi.removeCategory(id));
      return value === undefined ? outcome : { ...outcome, released: value.released };
    },
    [write]
  );

  return {
    own,
    maxCategories: data?.max_categories,
    nameMaxChars: data?.name_max_chars,
    // Derived from the ABSENCE of an answer, never from `loading`: a re-read
    // raises `loading` again, and a list keyed on it would blank the dialog
    // under the person's hands after every write.
    firstLoad: enabled && data === undefined && !error,
    error: !!error,
    create,
    update,
    remove,
  };
}
