'use client';

/**
 * useRelations — the personal CRM (N-09), read-only.
 *
 * Two hooks over the read-only `/relations` API: the overview and one
 * relationship's 360° detail. Same `useApiQuery` doctrine as the rest of the
 * app; nothing writes here — acting on a relationship is a chat deep link.
 */

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
}

export function useRelationsOverview() {
  const { data, loading, error } = useApiQuery<RelationsOverview>('/relations', {
    componentName: 'RelationsOverview',
    initialData: { relations: [] },
  });
  return { relations: data?.relations ?? [], loading, error: !!error };
}

export function useRelationDetail(name: string | null) {
  const { data, loading, error } = useApiQuery<RelationDetail>(
    name ? `/relations/${encodeURIComponent(name)}` : '',
    { componentName: 'RelationDetail', enabled: !!name }
  );
  return { detail: data ?? null, loading, error: !!error };
}
