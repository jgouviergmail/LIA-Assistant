/**
 * The progressive dashboard's reads (spec 2026-10-21 §5.8, D3).
 *
 * One page load is one ACT: `GET /briefing/cards/initial` answers at once with
 * every section that needs no slow source and lists the others `pending`; each
 * pending section is then read on its own (`GET /briefing/sections/{name}?act=`),
 * at most `section_concurrency` at a time so a browser on HTTP/1.1 never queues
 * the page behind its SSE stream; the greeting and synthesis are asked for once
 * every section settled (`POST /briefing/text`). `useBriefing` keeps the public
 * shape and its protections; this module holds the act's mechanics.
 */
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react';
import apiClient, { ApiError } from '@/lib/api-client';
import { trackClientTiming, type ClientTiming } from '@/lib/product-telemetry';
import type {
  BriefingInitialResponse,
  BriefingSection,
  BriefingWindows,
  CardSection,
  CardsBundle,
  TextSection,
} from '@/types/briefing';

export const ENDPOINT_INITIAL = '/briefing/cards/initial';
export const ENDPOINT_TEXT = '/briefing/text';

/** The act expired or its context changed (language, timezone, local day, hidden set). */
const CONTEXT_CHANGED = 'briefing_context_changed';

export interface BriefingText {
  greeting: TextSection;
  synthesis: TextSection | null;
}

export function sectionEndpoint(name: BriefingSection): string {
  return `/briefing/sections/${name}`;
}

export function sectionRefreshEndpoint(name: BriefingSection): string {
  return `/briefing/sections/${name}/refresh`;
}

/** The server asks for a new initial load: the act can no longer be continued. */
export function isContextChanged(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false;
  const detail = (error.data as { detail?: { code?: unknown } } | undefined)?.detail;
  return detail?.code === CONTEXT_CHANGED;
}

/** The sections of the bundle still waiting for their own read. */
export function pendingSections(bundle: BriefingInitialResponse | undefined): BriefingSection[] {
  if (!bundle) return [];
  return (Object.keys(bundle.cards) as BriefingSection[]).filter(
    name => bundle.cards[name]?.status === 'pending'
  );
}

/** One settled section merged into the act's bundle. */
export function withSection(
  bundle: BriefingInitialResponse,
  name: BriefingSection,
  section: CardSection
): BriefingInitialResponse {
  return {
    ...bundle,
    cards: { ...bundle.cards, [name]: section } as CardsBundle,
    pending: bundle.pending.filter(pending => pending !== name),
  };
}

/** A whole bundle from a refresh route, kept on the act it belongs to (no act: no text read). */
export function withBundle(
  current: BriefingInitialResponse | undefined,
  fresh: { cards: CardsBundle; windows: BriefingWindows }
): BriefingInitialResponse {
  return {
    act: current?.act ?? '',
    act_expires_at: current?.act_expires_at ?? '',
    section_concurrency: current?.section_concurrency ?? 1,
    cards: fresh.cards,
    windows: fresh.windows,
    pending: [],
  };
}

/** A section whose own read failed: an error card offering its retry, never a hole. */
function failedSection(): CardSection {
  const at = new Date().toISOString();
  return {
    status: 'error',
    data: null,
    generated_at: at,
    error_code: 'internal',
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: at,
  };
}

/** Run `read` over `items`, at most `limit` at once; resolves when every read settled. */
export async function readAtMost<T>(
  items: readonly T[],
  limit: number,
  read: (item: T) => Promise<void>
): Promise<void> {
  const queue = [...items];
  const worker = async () => {
    for (let item = queue.shift(); item !== undefined; item = queue.shift()) await read(item);
  };
  const workers = Math.max(1, Math.min(limit, queue.length));
  await Promise.all(Array.from({ length: workers }, worker));
}

interface Scope {
  controller: AbortController;
}

interface PendingReadsOptions {
  /** The act's bundle as the query holds it. */
  bundle: BriefingInitialResponse | undefined;
  /** The newest accepted bundle (merges land on it, never on a render's copy). */
  latest: MutableRefObject<BriefingInitialResponse | undefined>;
  /** Each section's read revision: a newer read of a section drops an older answer. */
  revisions: MutableRefObject<Map<BriefingSection, number>>;
  scope: MutableRefObject<Scope | null>;
  isCurrent: () => boolean;
  accept: (next: BriefingInitialResponse) => void;
  /** The act can no longer be continued: start a new initial load (false: no more allowed). */
  restart: () => boolean;
}

/**
 * Read the act's pending sections, at most `section_concurrency` at once.
 *
 * A read is started once per act and request scope: a suspended page aborts
 * its reads, and the scope it resumes with reads what is still pending. An
 * answer lands only for the current account, scope and act, and only when no
 * newer read of the same section started meanwhile (a refresh).
 */
export function usePendingSectionReads({
  bundle,
  latest,
  revisions,
  scope,
  isCurrent,
  accept,
  restart,
}: PendingReadsOptions): void {
  const started = useRef<{ act: string; scope: Scope | null } | null>(null);
  useEffect(() => {
    const act = bundle?.act;
    const names = pendingSections(bundle);
    const current = scope.current;
    if (!act || !names.length || !isCurrent()) return;
    if (started.current?.act === act && started.current.scope === current) return;
    started.current = { act, scope: current };
    let restarted = false;
    void readAtMost(names, bundle.section_concurrency, async name => {
      const revision = revisions.current.get(name) ?? 0;
      const applies = () =>
        !restarted &&
        isCurrent() &&
        scope.current === current &&
        latest.current?.act === act &&
        (revisions.current.get(name) ?? 0) === revision;
      if (!applies()) return;
      let section: CardSection;
      try {
        section = await apiClient.get<CardSection>(sectionEndpoint(name), {
          params: { act },
          signal: current?.controller.signal,
        });
      } catch (error) {
        if (!applies()) return;
        if (isContextChanged(error) && restart()) {
          restarted = true;
          return;
        }
        section = failedSection();
      }
      if (applies() && latest.current) accept(withSection(latest.current, name, section));
    });
  }, [bundle, latest, revisions, scope, isCurrent, accept, restart]);
}

interface TextState {
  lifetime: unknown;
  data: BriefingText | undefined;
  loading: boolean;
  error: Error | null;
}

/** The act's text, owned by one account lifetime: another lifetime starts empty. */
export function useActText(lifetime: unknown) {
  const [state, setState] = useState<TextState>({
    lifetime,
    data: undefined,
    loading: false,
    error: null,
  });
  const current: TextState =
    state.lifetime === lifetime
      ? state
      : { lifetime, data: undefined, loading: false, error: null };
  const update = useCallback(
    (patch: Partial<Omit<TextState, 'lifetime'>>) =>
      setState(previous => ({
        ...(previous.lifetime === lifetime
          ? previous
          : { lifetime, data: undefined, loading: false, error: null }),
        ...patch,
      })),
    [lifetime]
  );
  return { data: current.data, loading: current.loading, error: current.error, update };
}

/**
 * The dashboard's journey timings (spec 2026-10-21 O2), once per load: from the
 * load's start to its first card, to its last settled card, and to its text.
 *
 * @param lifetime The account lifetime one load belongs to.
 * @param active Whether the dashboard is being read (an inactive one starts no clock).
 * @param bundle The act's bundle as the page holds it.
 * @param hasText Whether the act's text arrived.
 */
export function useLoadTimings(
  lifetime: unknown,
  active: boolean,
  bundle: BriefingInitialResponse | undefined,
  hasText: boolean
): void {
  const load = useRef<{ lifetime: unknown; start: number; sent: Set<ClientTiming> } | null>(null);
  useEffect(() => {
    if (!active || load.current?.lifetime === lifetime) return;
    load.current = { lifetime, start: performance.now(), sent: new Set() };
  }, [lifetime, active]);
  useEffect(() => {
    const current = load.current;
    if (!current || current.lifetime !== lifetime) return;
    const emit = (metric: ClientTiming) => {
      if (current.sent.has(metric)) return;
      current.sent.add(metric);
      trackClientTiming(metric, (performance.now() - current.start) / 1000);
    };
    if (bundle) emit('dashboard_first_card');
    if (bundle && !pendingSections(bundle).length) emit('dashboard_all_cards');
    if (hasText) emit('dashboard_text');
  }, [lifetime, bundle, hasText]);
}
