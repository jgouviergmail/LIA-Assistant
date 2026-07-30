'use client';

/**
 * useRelations — the personal CRM (N-09 + favorites).
 *
 * Two read hooks over the `/relations` API (overview + one relationship's
 * 360° detail) and the ONE write verb of the CRM: the favorites star.
 * `toggleFavorite` is optimistic — the star flips locally at once, the
 * PUT/DELETE runs behind, and a failure flips it back (the peers-hook
 * doctrine: verbs return `{ ok }`, never leave state to a post-await read).
 */

import { useCallback, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';

/** How the relationship key was matched — honesty over false precision. */
export type IdentityConfidence = 'exact' | 'normalized';

export interface RelationOpenLoop {
  id: string;
  subject: string;
  direction: string;
  due_hint: string | null;
  days_open: number;
}

export interface RelationCall {
  id: string;
  objective: string;
  outcome: string | null;
  summary: string | null;
  created_at: string;
}

export interface RelationMemory {
  id: string;
  content: string;
}

export interface RelationSummary {
  display_name: string;
  identity_confidence: IdentityConfidence;
  open_loops_count: number;
  calls_count: number;
  last_interaction_at: string | null;
  /** Starred by the user — persisted server-side, survives signal expiry. */
  is_favorite: boolean;
  /** Also a connected LIA user (peers program bridge, read-only). */
  is_peer: boolean;
}

export interface RelationsOverview {
  relations: RelationSummary[];
}

export interface RelationDetail {
  display_name: string;
  identity_confidence: IdentityConfidence;
  open_loops: RelationOpenLoop[];
  recent_calls: RelationCall[];
  memories: RelationMemory[];
  is_favorite: boolean;
  is_peer: boolean;
}

export function useRelationsOverview() {
  const { data, loading, error, refetch } = useApiQuery<RelationsOverview>('/relations', {
    componentName: 'RelationsOverview',
    initialData: { relations: [] },
  });
  // Optimistic star state: name -> flipped value, cleared on refetch/failure.
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const put = useApiMutation({ method: 'PUT', componentName: 'RelationsFavorite' });
  const del = useApiMutation({ method: 'DELETE', componentName: 'RelationsFavorite' });

  const toggleFavorite = useCallback(
    async (name: string, nextValue: boolean): Promise<{ ok: boolean }> => {
      setOverrides(prev => ({ ...prev, [name]: nextValue }));
      try {
        const endpoint = `/relations/favorites/${encodeURIComponent(name)}`;
        if (nextValue) {
          await put.mutate(endpoint);
        } else {
          await del.mutate(endpoint);
        }
        // Reconcile: once the fresh overview lands it carries the server
        // truth — dropping the override then lets any LATER server-side
        // change (another tab, another device) show through again.
        void Promise.resolve(refetch()).then(() =>
          setOverrides(prev => {
            const next = { ...prev };
            delete next[name];
            return next;
          })
        );
        return { ok: true };
      } catch {
        // Roll the optimistic flip back — the server said no.
        setOverrides(prev => {
          const next = { ...prev };
          delete next[name];
          return next;
        });
        return { ok: false };
      }
    },
    [put, del, refetch]
  );

  const relations = (data?.relations ?? []).map(relation =>
    relation.display_name in overrides
      ? { ...relation, is_favorite: overrides[relation.display_name] }
      : relation
  );

  return { relations, loading, error: !!error, toggleFavorite };
}

export function useRelationDetail(name: string | null) {
  const { data, loading, error } = useApiQuery<RelationDetail>(
    name ? `/relations/${encodeURIComponent(name)}` : '',
    { componentName: 'RelationDetail', enabled: !!name }
  );
  return { detail: data ?? null, loading, error: !!error };
}
