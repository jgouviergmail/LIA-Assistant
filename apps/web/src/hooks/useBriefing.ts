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
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type {
  BriefingResponse,
  BriefingWindows,
  CardsBundle,
  RefreshRequest,
  RefreshScope,
  TextSection,
} from '@/types/briefing';

interface CardsResponse {
  cards: CardsBundle;
  windows: BriefingWindows;
}

interface SynthesisResponse {
  greeting: TextSection;
  synthesis: TextSection | null;
}

export interface UseBriefingResult {
  /** Cards bundle (fast — no LLM). undefined while initial query is in flight. */
  cards: CardsBundle | undefined;
  /** The windows the cards were built with, from the same response. */
  windows: BriefingWindows | undefined;
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
const ENDPOINT_REFRESH_CARDS = '/briefing/refresh-cards';
const releaseReminderOverride = () => {};

export function useBriefing(): UseBriefingResult {
  const cardsQuery = useApplicationAccountQuery<CardsResponse>(ENDPOINT_CARDS, 'TodayBriefing.cards');
  const synthesisQuery = useApplicationAccountQuery<SynthesisResponse>(ENDPOINT_SYNTHESIS, 'TodayBriefing.synthesis');
  const { ownerId, lifetime, isCurrent, refetch: refetchCards } = cardsQuery;
  // Reminder cards are always live at the source; rereading them calls no LLM.
  useApplicationResourceSync(ownerId, 'reminders', refetchCards, releaseReminderOverride);

  const [refreshing, setRefreshing] = useState({ lifetime, sections: new Set<RefreshScope>() });
  const refreshingSections = refreshing.lifetime === lifetime ? refreshing.sections : new Set<RefreshScope>();

  const refetchSection = useCallback(
    async (section: RefreshScope) => {
      if (!isCurrent()) return;
      setRefreshing(prev => {
        const next = new Set(prev.lifetime === lifetime ? prev.sections : []);
        next.add(section);
        return { lifetime, sections: next };
      });
      try {
        const payload: RefreshRequest = { sections: [section] };
        if (section === 'all') {
          // Global refresh: the LLM texts summarize the cards, regenerate both.
          const fresh = await apiClient.post<BriefingResponse>(ENDPOINT_REFRESH, payload);
          if (!isCurrent()) return;
          cardsQuery.setData({ cards: fresh.cards, windows: fresh.windows });
          synthesisQuery.setData({ greeting: fresh.greeting, synthesis: fresh.synthesis });
        } else {
          // D-04: a per-card retry must not pay two LLM calls — cards only.
          const fresh = await apiClient.post<CardsResponse>(ENDPOINT_REFRESH_CARDS, payload);
          if (!isCurrent()) return;
          cardsQuery.setData({ cards: fresh.cards, windows: fresh.windows });
        }
      } finally {
        if (isCurrent()) {
          setRefreshing(prev => {
            const next = new Set(prev.lifetime === lifetime ? prev.sections : []);
            next.delete(section);
            return { lifetime, sections: next };
          });
        }
      }
    },
    [cardsQuery, synthesisQuery, isCurrent, lifetime]
  );

  const refetchAll = useCallback(async () => {
    await Promise.all([cardsQuery.refetch(), synthesisQuery.refetch()]);
  }, [cardsQuery, synthesisQuery]);

  return {
    cards: cardsQuery.data?.cards,
    windows: cardsQuery.data?.windows,
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
