/** Independent cards and text reads keep the dashboard progressive. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import apiClient from '@/lib/api-client';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { subscribeApplicationResource } from '@/lib/application-resources';
import type {
  BriefingResponse,
  BriefingSection,
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
  cards: CardsBundle | undefined;
  windows: BriefingWindows | undefined;
  text: SynthesisResponse | undefined;
  loading: boolean;
  cardsLoading: boolean;
  textLoading: boolean;
  /** A previous text attempt ended without usable text; only explicit retry may regenerate it. */
  textUnavailable: boolean;
  error: Error | null;
  /** Retry independent initial reads after an error. */
  refetchAll: () => Promise<void>;
  /** Explicit manual refresh; only 'all' regenerates greeting and synthesis. */
  refetchSection: (section: RefreshScope) => Promise<void>;
  /** Reread after a committed mutation, without generating LLM text. */
  invalidateSection: (section: BriefingSection) => Promise<void>;
  refreshingSections: Set<RefreshScope>;
}
const ENDPOINT_CARDS = '/briefing/cards';
const ENDPOINT_SYNTHESIS = '/briefing/synthesis';
const ENDPOINT_REFRESH = '/briefing/refresh';
const ENDPOINT_REFRESH_CARDS = '/briefing/refresh-cards';

function visibleCards(cards: CardsBundle | undefined, hideSms: boolean): CardsBundle | undefined {
  const sms = cards?.sms;
  if (!hideSms || !cards || !sms?.data) return cards;
  return { ...cards, sms: { ...sms, data: { ...sms.data, items: [] } } };
}

/** What the text read has done in this lifetime, as the two states the page draws. */
interface TextProgress {
  enabled: boolean;
  /** An account owns this lifetime, so its initial text read will be issued. */
  owned: boolean;
  /** The initial text read of this lifetime has been issued. */
  requested: boolean;
  loading: boolean;
  hasText: boolean;
}

/**
 * The text's derived states. The initial read is issued after the first
 * commit, so the query is idle on the first frames: a text this lifetime WILL
 * ask for is loading from the first render — the welcome and the synthesis
 * hold their skeletons instead of flashing absent, then shifting when the read
 * starts. A text asked for that ended without one is unavailable: only an
 * explicit retry may buy another.
 */
function textStatus(progress: TextProgress): { textLoading: boolean; textUnavailable: boolean } {
  const { enabled, owned, requested, loading, hasText } = progress;
  const awaited = enabled && owned && !requested && !hasText;
  return {
    textLoading: loading || awaited,
    textUnavailable: enabled && requested && !loading && !hasText,
  };
}

export function useBriefing(enabled = true): UseBriefingResult {
  const cardsQuery = useApplicationAccountQuery<CardsResponse>(
    ENDPOINT_CARDS,
    'TodayBriefing.cards',
    enabled
  );
  const synthesisQuery = useApplicationAccountQuery<SynthesisResponse>(
    ENDPOINT_SYNTHESIS,
    'TodayBriefing.synthesis',
    enabled,
    undefined,
    { autoFetch: false }
  );
  const { ownerId, lifetime, isCurrent: isOwnerCurrent, acceptData: acceptCards } = cardsQuery;
  const { acceptData: acceptText, setData: setText, refetch: rereadText } = synthesisQuery;
  const activity = useMemo(() => ({ enabled, lifetime }), [enabled, lifetime]);
  const requestScope = useRef<{ activity: typeof activity; controller: AbortController } | null>(
    null
  );
  useEffect(() => {
    const scope = { activity, controller: new AbortController() };
    requestScope.current = scope;
    return () => {
      scope.controller.abort();
      if (requestScope.current === scope) requestScope.current = null;
    };
  }, [activity]);
  const isCurrent = useCallback(
    () => enabled && isOwnerCurrent() && requestScope.current?.activity === activity,
    [enabled, isOwnerCurrent, activity]
  );
  const initialText = useRef<typeof lifetime | null>(null);
  const [textRequested, setTextRequested] = useState<typeof lifetime | null>(null);
  useEffect(() => {
    let current = true;
    queueMicrotask(() => {
      if (!current || !isCurrent() || initialText.current === lifetime) return;
      initialText.current = lifetime;
      setTextRequested(lifetime);
      // This attempt may already have cost money when aborted. Only an explicit
      // retry may issue another text request; the query publishes its own error.
      void rereadText().catch(() => {});
    });
    return () => {
      current = false;
    };
  }, [isCurrent, lifetime, rereadText]);
  const [smsBarrier, setSmsBarrier] = useState({ lifetime, closed: false });
  const [refreshing, setRefreshing] = useState({ lifetime, sections: new Set<RefreshScope>() });
  const pending = useRef({ lifetime, sections: new Set<RefreshScope>() });
  const [refreshFailure, setRefreshFailure] = useState({ lifetime, error: null as Error | null });
  const refreshingSections =
    refreshing.lifetime === lifetime ? refreshing.sections : new Set<RefreshScope>();
  const invalidated = useRef({ lifetime, sections: new Set<BriefingSection>() });
  const waitingForCards = useRef(false);
  const dirtySections = useCallback(() => {
    if (invalidated.current.lifetime !== lifetime)
      invalidated.current = { lifetime, sections: new Set() };
    const dirty = invalidated.current.sections;
    for (const section of dirty) {
      if (cardsQuery.data?.cards[section]?.status === 'hidden') dirty.delete(section);
    }
    return dirty;
  }, [lifetime, cardsQuery.data]);
  const cardsRevision = useRef(0);
  const textRevision = useRef(0);
  const beginCardsRead = useCallback(() => {
    const revision = ++cardsRevision.current;
    const scope = requestScope.current;
    return () =>
      isCurrent() && requestScope.current === scope && cardsRevision.current === revision;
  }, [isCurrent]);
  const beginTextRead = useCallback(() => {
    const revision = ++textRevision.current;
    const scope = requestScope.current;
    return () => isCurrent() && requestScope.current === scope && textRevision.current === revision;
  }, [isCurrent]);

  // Matching forced builds share a server-side single_flight snapshot. A read
  // after a mutation must START after our preceding build has actually ended.
  const flight = useRef({ lifetime, settled: Promise.resolve() });
  const afterFlight = useCallback(
    (current: () => boolean, read: () => Promise<void>) => {
      if (flight.current.lifetime !== lifetime)
        flight.current = { lifetime, settled: Promise.resolve() };
      const execute = async () => {
        if (!current()) return;
        try {
          await read();
        } catch (error) {
          if (current()) {
            setRefreshFailure({
              lifetime,
              error: error instanceof Error ? error : new Error('Briefing refresh failed'),
            });
          }
        }
      };
      const next = flight.current.settled.then(execute);
      flight.current.settled = next;
      return next;
    },
    [lifetime]
  );

  const readForcedCards = useCallback(
    async (dirty: Set<BriefingSection>, current: () => boolean) => {
      if (!dirty.size) return;
      const fresh = await apiClient.post<CardsResponse>(
        ENDPOINT_REFRESH_CARDS,
        {
          sections: [...dirty],
        } satisfies RefreshRequest,
        { signal: requestScope.current?.controller.signal }
      );
      if (current()) {
        acceptCards(fresh);
        setSmsBarrier({ lifetime, closed: false });
        dirty.clear();
      }
    },
    [acceptCards, lifetime]
  );

  const invalidateSection = useCallback(
    async (section: BriefingSection) => {
      if (!isOwnerCurrent()) return;
      const dirty = dirtySections();
      if (cardsQuery.data?.cards[section]?.status === 'hidden') return;
      dirty.add(section);
      if (!isCurrent()) {
        waitingForCards.current = true;
        return;
      }
      const current = beginCardsRead();
      setRefreshFailure({ lifetime, error: null });
      if (!cardsQuery.data) {
        // Preserve external changes during first load. Once visibility is known,
        // force only visible cards; never force a hidden section (the API refuses it).
        waitingForCards.current = true;
        return;
      }
      await afterFlight(current, () => readForcedCards(dirty, current));
    },
    [
      isCurrent,
      isOwnerCurrent,
      dirtySections,
      cardsQuery.data,
      beginCardsRead,
      lifetime,
      afterFlight,
      readForcedCards,
    ]
  );

  useEffect(() => {
    if (!cardsQuery.data || !waitingForCards.current || !isCurrent()) return;
    waitingForCards.current = false;
    const [section] = dirtySections();
    if (section) void invalidateSection(section);
  }, [cardsQuery.data, dirtySections, invalidateSection, isCurrent]);
  useEffect(() => {
    if (!ownerId) return;
    const reminders = subscribeApplicationResource(ownerId, 'reminders', () => {
      void invalidateSection('reminders');
    });
    const sms = subscribeApplicationResource(ownerId, 'sms', () => {
      // Cancel a current GET and supersede any paid manual refresh in flight.
      // The next text generation remains an explicit user action.
      textRevision.current += 1;
      setSmsBarrier({ lifetime, closed: true });
      // A suspended query cannot accept external data. Clearing its owner-local
      // cache still prevents withdrawn SMS text resurfacing on reactivation.
      if (!acceptText(undefined)) setText(undefined);
      void invalidateSection('sms');
    });
    return () => {
      reminders();
      sms();
    };
  }, [ownerId, lifetime, invalidateSection, acceptText, setText]);

  const refetchSection = useCallback(
    async (section: RefreshScope) => {
      if (!isCurrent()) return;
      if (pending.current.lifetime !== lifetime)
        pending.current = { lifetime, sections: new Set() };
      const active = pending.current.sections;
      // This synchronous manual guard prevents a double press buying two texts.
      // Mutation invalidations bypass it and retain all changed sections.
      if (active.has(section) || active.has('all') || (section === 'all' && active.size > 0))
        return;
      const dirty = dirtySections();
      if (section !== 'all') dirty.add(section);
      active.add(section);
      const current = beginCardsRead();
      const textCurrent = section === 'all' ? beginTextRead() : () => false;
      setRefreshFailure({ lifetime, error: null });
      setRefreshing(prev => ({
        lifetime,
        sections: new Set(prev.lifetime === lifetime ? prev.sections : []).add(section),
      }));
      try {
        await afterFlight(
          () => current() || textCurrent(),
          async () => {
            if (section !== 'all') return readForcedCards(dirty, current);
            const fresh = await apiClient.post<BriefingResponse>(
              ENDPOINT_REFRESH,
              {
                sections: ['all'],
              },
              { signal: requestScope.current?.controller.signal }
            );
            // A first successful bundle also supplies visibility for invalidations
            // held during an initial GET failure. Keep dirty until its forced drain.
            if (current() || (isCurrent() && waitingForCards.current)) {
              acceptCards({ cards: fresh.cards, windows: fresh.windows });
              if (current()) {
                dirty.clear();
                setSmsBarrier({ lifetime, closed: false });
              }
            }
            // A cards-only mutation did not replace this paid text generation.
            // Keep its original generated_at/usage unless a newer text read won.
            if (textCurrent()) acceptText({ greeting: fresh.greeting, synthesis: fresh.synthesis });
          }
        );
      } finally {
        active.delete(section);
        if (isCurrent()) {
          setRefreshing(prev => {
            const sections = new Set(prev.lifetime === lifetime ? prev.sections : []);
            sections.delete(section);
            return { lifetime, sections };
          });
        }
      }
    },
    [
      isCurrent,
      lifetime,
      dirtySections,
      beginCardsRead,
      beginTextRead,
      afterFlight,
      readForcedCards,
      acceptCards,
      acceptText,
    ]
  );

  const refetchAll = useCallback(async () => {
    if (!isCurrent()) return;
    beginCardsRead();
    beginTextRead();
    setRefreshFailure({ lifetime, error: null });
    const [dirtySection] = dirtySections();
    // First-load failures must still retry GET to learn visibility. The effect
    // above then drains any invalidation held while that initial read failed.
    const cardsRead =
      dirtySection && cardsQuery.data
        ? invalidateSection(dirtySection)
        : afterFlight(isCurrent, cardsQuery.refetch);
    await Promise.allSettled([cardsRead, rereadText()]);
  }, [
    isCurrent,
    beginCardsRead,
    beginTextRead,
    lifetime,
    dirtySections,
    cardsQuery,
    invalidateSection,
    afterFlight,
    rereadText,
  ]);

  const { textLoading, textUnavailable } = textStatus({
    enabled,
    owned: !!lifetime.ownerId,
    requested: textRequested === lifetime,
    loading: synthesisQuery.loading,
    hasText: !!synthesisQuery.data,
  });
  return {
    cards: visibleCards(
      cardsQuery.data?.cards,
      smsBarrier.lifetime === lifetime && smsBarrier.closed
    ),
    windows: cardsQuery.data?.windows,
    text: synthesisQuery.data,
    loading: cardsQuery.loading || textLoading,
    cardsLoading: cardsQuery.loading,
    textLoading,
    textUnavailable,
    error:
      cardsQuery.error ||
      synthesisQuery.error ||
      (refreshFailure.lifetime === lifetime ? refreshFailure.error : null),
    refetchAll,
    refetchSection,
    invalidateSection,
    refreshingSections,
  };
}
