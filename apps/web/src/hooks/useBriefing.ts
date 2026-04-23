/**
 * useBriefing — Today dashboard hook.
 *
 * Splits the network into TWO independent queries so the cards can render
 * immediately while the LLM-generated greeting + synthesis arrive a moment
 * later (non-blocking UX).
 *
 *   - GET /briefing/cards     → CardsBundle (fast)
 *   - GET /briefing/synthesis → greeting + synthesis (LLM-bound)
 *
 * Refresh:
 *   - POST /briefing/refresh  → returns full payload (cards + greeting + synthesis)
 *     Triggered when user clicks 🔄 on a card or "refresh all".
 */

import { useCallback, useState } from 'react';
import apiClient from '@/lib/api-client';
import { useApiQuery } from '@/hooks/useApiQuery';
import type {
  BriefingResponse,
  CardsBundle,
  RefreshRequest,
  RefreshScope,
  TextSection,
} from '@/types/briefing';

interface CardsResponse {
  cards: CardsBundle;
}

interface SynthesisResponse {
  greeting: TextSection;
  synthesis: TextSection | null;
}

export interface UseBriefingResult {
  /** Cards bundle (fast — no LLM). undefined while initial query is in flight. */
  cards: CardsBundle | undefined;
  /** Greeting + synthesis (LLM). undefined while LLM call is in flight. */
  text: SynthesisResponse | undefined;
  /** True while either initial query is loading. */
  loading: boolean;
  /** True specifically while the cards query is loading. */
  cardsLoading: boolean;
  /** True specifically while the synthesis query is loading. */
  textLoading: boolean;
  /** Error from any of the queries. */
  error: Error | null;
  /** Refresh both cards and synthesis from scratch. */
  refetchAll: () => Promise<void>;
  /**
   * Force-refresh one section (or 'all') via POST /briefing/refresh.
   * Backend regenerates greeting + synthesis for consistency.
   */
  refetchSection: (section: RefreshScope) => Promise<void>;
  /** Sections currently in flight (for per-card spinner UX). */
  refreshingSections: Set<RefreshScope>;
}

const ENDPOINT_CARDS = '/briefing/cards';
const ENDPOINT_SYNTHESIS = '/briefing/synthesis';
const ENDPOINT_REFRESH = '/briefing/refresh';

export function useBriefing(): UseBriefingResult {
  const cardsQuery = useApiQuery<CardsResponse>(ENDPOINT_CARDS, {
    componentName: 'TodayBriefing.cards',
  });
  const synthesisQuery = useApiQuery<SynthesisResponse>(ENDPOINT_SYNTHESIS, {
    componentName: 'TodayBriefing.synthesis',
  });

  const [refreshingSections, setRefreshing] = useState<Set<RefreshScope>>(new Set());

  const refetchSection = useCallback(
    async (section: RefreshScope) => {
      setRefreshing(prev => {
        const next = new Set(prev);
        next.add(section);
        return next;
      });
      try {
        const payload: RefreshRequest = { sections: [section] };
        const fresh = await apiClient.post<BriefingResponse>(ENDPOINT_REFRESH, payload);
        // Swap both queries with the refreshed payload.
        cardsQuery.setData({ cards: fresh.cards });
        synthesisQuery.setData({ greeting: fresh.greeting, synthesis: fresh.synthesis });
      } finally {
        setRefreshing(prev => {
          const next = new Set(prev);
          next.delete(section);
          return next;
        });
      }
    },
    [cardsQuery, synthesisQuery],
  );

  const refetchAll = useCallback(async () => {
    await Promise.all([cardsQuery.refetch(), synthesisQuery.refetch()]);
  }, [cardsQuery, synthesisQuery]);

  return {
    cards: cardsQuery.data?.cards,
    text: synthesisQuery.data,
    loading: cardsQuery.loading || synthesisQuery.loading,
    cardsLoading: cardsQuery.loading,
    textLoading: synthesisQuery.loading,
    error: cardsQuery.error || synthesisQuery.error,
    refetchAll,
    refetchSection,
    refreshingSections,
  };
}
