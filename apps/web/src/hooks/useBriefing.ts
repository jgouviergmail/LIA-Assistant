/**
 * The dashboard's reads, one ACT per page load (spec 2026-10-21 §5.8, D3).
 *
 * The initial read shows every section that needs no slow source; the pending
 * ones follow one request each (`useBriefingProgressive`); the text is asked for
 * once every section settled. The protections are this hook's: the SMS barrier,
 * the queued invalidations, the double-press guard and the account lifetime.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import apiClient from '@/lib/api-client';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import {
  ENDPOINT_INITIAL,
  ENDPOINT_TEXT,
  isContextChanged,
  pendingSections,
  sectionRefreshEndpoint,
  useActText,
  useLoadTimings,
  usePendingSectionReads,
  withBundle,
  withSection,
  type BriefingText,
} from '@/hooks/useBriefingProgressive';
import { subscribeApplicationResource } from '@/lib/application-resources';
import type {
  BriefingInitialResponse,
  BriefingResponse,
  BriefingSection,
  BriefingTextResponse,
  BriefingWindows,
  CardSection,
  CardsBundle,
  RefreshRequest,
  RefreshScope,
} from '@/types/briefing';

interface CardsResponse {
  cards: CardsBundle;
  windows: BriefingWindows;
}
export interface UseBriefingResult {
  cards: CardsBundle | undefined;
  windows: BriefingWindows | undefined;
  text: BriefingText | undefined;
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
const ENDPOINT_REFRESH = '/briefing/refresh';
/** Automatic new acts per account lifetime before a refused act becomes an error. */
const MAX_ACT_RESTARTS = 2;
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
  /** The initial read failed: there is no act whose text could be awaited. */
  orphaned: boolean;
  loading: boolean;
  hasText: boolean;
}

/**
 * The text's derived states. The initial read waits for the act's sections to
 * settle, so the read is idle on the first frames: a text this lifetime WILL
 * ask for is loading from the first render — the welcome and the synthesis
 * hold their skeletons instead of flashing absent, then shifting when the read
 * starts. A text asked for that ended without one is unavailable: only an
 * explicit retry may buy another.
 */
function textStatus(progress: TextProgress): { textLoading: boolean; textUnavailable: boolean } {
  const { enabled, owned, requested, orphaned, loading, hasText } = progress;
  const awaited = enabled && owned && !requested && !orphaned && !hasText;
  return {
    textLoading: loading || awaited,
    textUnavailable: enabled && requested && !loading && !hasText,
  };
}

export function useBriefing(enabled = true): UseBriefingResult {
  const cardsQuery = useApplicationAccountQuery<BriefingInitialResponse>(
    ENDPOINT_INITIAL,
    'TodayBriefing.cards',
    enabled
  );
  const { ownerId, lifetime, isCurrent: isOwnerCurrent, acceptData: acceptInitial } = cardsQuery;
  const textState = useActText(lifetime);
  const { update: updateText } = textState;
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

  // The newest accepted bundle (section answers merge onto it) and each
  // section's read revision (a newer read of a section drops an older answer).
  const latest = useRef<BriefingInitialResponse | undefined>(undefined);
  const revisions = useRef(new Map<BriefingSection, number>());
  useEffect(() => {
    if (cardsQuery.data?.act !== latest.current?.act) latest.current = cardsQuery.data;
  }, [cardsQuery.data]);
  const acceptBundle = useCallback(
    (next: BriefingInitialResponse) => {
      if (!acceptInitial(next)) return false;
      latest.current = next;
      return true;
    },
    [acceptInitial]
  );
  const supersede = useCallback((names: readonly BriefingSection[]) => {
    for (const name of names) revisions.current.set(name, (revisions.current.get(name) ?? 0) + 1);
  }, []);

  const initialText = useRef<typeof lifetime | null>(null);
  const [textRequested, setTextRequested] = useState<typeof lifetime | null>(null);
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

  // A new initial load when the act can no longer be continued (409) — bounded per
  // lifetime, so a context that keeps changing cannot loop; an explicit retry resets it.
  const restarts = useRef({ lifetime, count: 0 });
  const restartAct = useCallback(() => {
    if (restarts.current.lifetime !== lifetime) restarts.current = { lifetime, count: 0 };
    if (restarts.current.count >= MAX_ACT_RESTARTS) return false;
    restarts.current.count += 1;
    void afterFlight(isCurrent, cardsQuery.refetch);
    return true;
  }, [afterFlight, isCurrent, cardsQuery.refetch, lifetime]);
  usePendingSectionReads({
    bundle: cardsQuery.data,
    latest,
    revisions,
    scope: requestScope,
    isCurrent,
    accept: acceptBundle,
    restart: restartAct,
  });

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
        supersede(Object.keys(fresh.cards) as BriefingSection[]);
        acceptBundle(withBundle(latest.current, fresh));
        setSmsBarrier({ lifetime, closed: false });
        dirty.clear();
      }
    },
    [acceptBundle, supersede, lifetime]
  );

  /** One section re-read on its own route: no other card moves and no text is bought. */
  const readOneSection = useCallback(
    async (section: BriefingSection, dirty: Set<BriefingSection>, current: () => boolean) => {
      supersede([section]);
      const fresh = await apiClient.post<CardSection>(sectionRefreshEndpoint(section), undefined, {
        signal: requestScope.current?.controller.signal,
      });
      if (current() && latest.current) {
        acceptBundle(withSection(latest.current, section, fresh));
        if (section === 'sms') setSmsBarrier({ lifetime, closed: false });
        dirty.delete(section);
      }
    },
    [acceptBundle, supersede, lifetime]
  );

  /**
   * The changed sections, each on its own route while an act serves the page: the bundle
   * route would also re-read, live, every section still pending on its own request — one
   * paid read bought twice. Without an act (a first load that failed) it is the only route.
   */
  const readDirty = useCallback(
    async (dirty: Set<BriefingSection>, current: () => boolean) => {
      if (!dirty.size) return;
      if (!latest.current?.act) return readForcedCards(dirty, current);
      await Promise.all([...dirty].map(section => readOneSection(section, dirty, current)));
    },
    [readForcedCards, readOneSection]
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
      await afterFlight(current, () => readDirty(dirty, current));
    },
    [
      isCurrent,
      isOwnerCurrent,
      dirtySections,
      cardsQuery.data,
      beginCardsRead,
      lifetime,
      afterFlight,
      readDirty,
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
      // Cancel a current read and supersede any paid manual refresh in flight.
      // The next text generation remains an explicit user action.
      textRevision.current += 1;
      setSmsBarrier({ lifetime, closed: true });
      updateText({ data: undefined, loading: false });
      void invalidateSection('sms');
    });
    return () => {
      reminders();
      sms();
    };
  }, [ownerId, lifetime, invalidateSection, updateText]);

  const readText = useCallback(
    async (act: string) => {
      const current = beginTextRead();
      const revision = textRevision.current;
      updateText({ loading: true, error: null });
      try {
        const answer = await apiClient.post<BriefingTextResponse>(
          ENDPOINT_TEXT,
          { act, force: false },
          { signal: requestScope.current?.controller.signal }
        );
        if (!current()) return;
        // Only a ready text is shown; an uncertain one is unavailable until an
        // explicit retry, and a stale one was written about SMS since withdrawn.
        updateText({
          data:
            answer.state === 'ready'
              ? { greeting: answer.greeting, synthesis: answer.synthesis }
              : undefined,
        });
        if (answer.state === 'sms_stale') {
          // As on the SMS event: hide the previews and reread the card.
          setSmsBarrier({ lifetime, closed: true });
          void invalidateSection('sms');
        }
      } catch (error) {
        if (!current()) return;
        if (isContextChanged(error) && restartAct()) {
          // Refused before anything was generated: the new act reads its text once its
          // own sections settled — awaited, never « unavailable » meanwhile (a retry
          // offered then bought a text of half the page).
          initialText.current = null;
          setTextRequested(null);
          return;
        }
        updateText({ error: error instanceof Error ? error : new Error('Briefing text failed') });
      } finally {
        if (textRevision.current === revision) updateText({ loading: false });
      }
    },
    [beginTextRead, updateText, restartAct, lifetime, invalidateSection]
  );

  // The initial text read: once per account lifetime, after every section settled.
  useEffect(() => {
    const bundle = cardsQuery.data;
    if (!bundle?.act || pendingSections(bundle).length || textState.data) return;
    if (initialText.current === lifetime || !isCurrent()) return;
    initialText.current = lifetime;
    setTextRequested(lifetime);
    // This attempt may already have cost money when aborted. Only an explicit
    // retry may issue another text request; the read publishes its own error.
    void readText(bundle.act);
  }, [cardsQuery.data, textState.data, lifetime, isCurrent, readText]);

  const refreshEverything = useCallback(
    async (current: () => boolean, textCurrent: () => boolean, dirty: Set<BriefingSection>) => {
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
        supersede(Object.keys(fresh.cards) as BriefingSection[]);
        acceptBundle(withBundle(latest.current, fresh));
        if (current()) {
          dirty.clear();
          setSmsBarrier({ lifetime, closed: false });
        }
      }
      // A cards-only mutation did not replace this paid text generation.
      // Keep its original generated_at/usage unless a newer text read won.
      if (textCurrent()) {
        initialText.current = lifetime;
        setTextRequested(lifetime);
        updateText({ data: { greeting: fresh.greeting, synthesis: fresh.synthesis }, error: null });
      }
    },
    [isCurrent, supersede, acceptBundle, lifetime, updateText]
  );

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
            if (section === 'all') return refreshEverything(current, textCurrent, dirty);
            // The card, and any other changed section, each on its own route: no text
            // is bought and no pending section is read twice (D3).
            return readDirty(dirty, current);
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
      readDirty,
      refreshEverything,
    ]
  );

  const refetchAll = useCallback(async () => {
    if (!isCurrent()) return;
    beginCardsRead();
    beginTextRead();
    restarts.current = { lifetime, count: 0 };
    setRefreshFailure({ lifetime, error: null });
    const [dirtySection] = dirtySections();
    const bundle = cardsQuery.data;
    if (!bundle?.act) {
      // First-load failures must retry the initial read to learn visibility. The
      // effect above then drains any invalidation held while it failed, and this
      // explicit retry grants the new act its text once its sections settle.
      initialText.current = null;
      setTextRequested(null);
      await afterFlight(isCurrent, cardsQuery.refetch);
      return;
    }
    const cardsRead = dirtySection ? invalidateSection(dirtySection) : Promise.resolve();
    if (pendingSections(bundle).length) {
      // Its sections still pending: the initial read follows them, never half a page.
      initialText.current = null;
      setTextRequested(null);
      await cardsRead;
      return;
    }
    initialText.current = lifetime;
    setTextRequested(lifetime);
    await Promise.allSettled([cardsRead, readText(bundle.act)]);
  }, [
    isCurrent,
    beginCardsRead,
    beginTextRead,
    lifetime,
    dirtySections,
    cardsQuery,
    invalidateSection,
    afterFlight,
    readText,
  ]);

  useLoadTimings(lifetime, enabled && !!lifetime.ownerId, cardsQuery.data, !!textState.data);

  const { textLoading, textUnavailable } = textStatus({
    enabled,
    owned: !!lifetime.ownerId,
    requested: textRequested === lifetime,
    orphaned: !!cardsQuery.error && !cardsQuery.data,
    loading: textState.loading,
    hasText: !!textState.data,
  });
  return {
    cards: visibleCards(
      cardsQuery.data?.cards,
      smsBarrier.lifetime === lifetime && smsBarrier.closed
    ),
    windows: cardsQuery.data?.windows,
    text: textState.data,
    loading: cardsQuery.loading || textLoading,
    cardsLoading: cardsQuery.loading,
    textLoading,
    textUnavailable,
    error:
      cardsQuery.error ||
      textState.error ||
      (refreshFailure.lifetime === lifetime ? refreshFailure.error : null),
    refetchAll,
    refetchSection,
    invalidateSection,
    refreshingSections,
  };
}
