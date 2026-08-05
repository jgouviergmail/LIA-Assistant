'use client';

/**
 * The chat's one-shot deep links — read LIVE, cleared through the History API.
 *
 * `?draft=` prefills, `?voice=1` spotlights push-to-talk, `?intent=` executes
 * (QW-24 / ADR-173). All three are one-shot: once acted upon they leave the URL
 * so a reload or a back cannot replay them.
 *
 * **Three rules, all three paid for in production on 2026-08-01.**
 *
 * 1. **Read live, never capture at mount.** A second deep link to the SAME
 *    route changes the query WITHOUT remounting the page, so a value frozen in
 *    `useState(() => …)` keeps executing the previous request. That is how a
 *    360° recap on one person, then another, then a third sent the FIRST one's
 *    sentence three times — the database holds it verbatim.
 * 2. **Clear through the History API, never `router.replace`.** A replace that
 *    only removes params is swallowed: the App Router restores the search
 *    params of the entry it already holds for the route (ADR-192, the same
 *    mechanism that sent one person's request for another's). The History API
 *    is the supported way to update the query without navigating, and Next
 *    syncs `useSearchParams` with it — so the latch still re-arms.
 * 3. **Clear `?intent=` only once it has been CONSUMED, never on arrival.** The
 *    auto-send waits for auth to resolve; clearing at mount wins that race and
 *    the request evaporates before anything can send it. (Measured: the scope
 *    PUT succeeded five times while the chat received nothing.) The old
 *    mount-capture was silently doing double duty here — it was also the buffer
 *    that let the send wait. `?draft=` and `?voice=` have no such wait: they are
 *    read during render, so they are cleared on arrival as before.
 *
 * A fourth behaviour was measured alongside them and stayed unexplained for a
 * day: `clearIntent` did not commit when it was the only router navigation of
 * the page's life, so a RELOAD re-executed the request. ADR-192 named the cause
 * — the App Router restores the search params of the entry it already holds —
 * and rule 2 above is the fix. The two are one defect seen from two sides.
 *
 * 4. **Refuse an `iid` that was already consumed** (ADR-210, paid for on
 *    2026-08-05). Rules 1-3 all police the CARRIER, and the carrier is
 *    replayable by design: the real navigation of ADR-192 records the intent
 *    URL as a browser-history VISIT, which `replaceState` cannot reach — the
 *    omnibox, a most-visited tile or a session restore resurrects it and the
 *    request re-executes ("Prépare une réponse au mail…" sent twice, 27 s
 *    apart, each cancelled by the user). Every click now travels with a
 *    one-shot `iid` (`chatIntentHref`) whose consumption is recorded in the
 *    ledger (`intent-replay-guard`); a resurrected URL carries a consumed iid
 *    and degrades to a VISIBLE draft — never a send, never a silent drop.
 *    Backend-emitted intent links carry no iid on purpose: each click on a
 *    durable "Run it now" link is a consent, replay across days included.
 *
 * The "act only once" latch is NOT here — it belongs to the consumer
 * (`useAutoSendIntent`), keyed on the VALUE, so that clearing the param is what
 * re-arms it and asking twice for the same person still counts twice.
 *
 * `?capability=`/`?subject=` (ADR-191) travel WITH `?intent=` and are cleared
 * in the same breath: they are one request, and a directive outliving its
 * sentence would attach this subject to the next, unrelated intent. The `iid`
 * is part of the same breath.
 */

import { useCallback, useEffect, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';

import { isIntentConsumed, markIntentConsumed } from '@/lib/intent-replay-guard';
import type { CapabilityDirectiveWire } from '@/types/directive';

/**
 * Capabilities a deep link may invoke, mirrored from the backend Literal.
 *
 * Read as an allowlist, never trusted: a hand-edited `?capability=` that is not
 * in this set yields no directive at all, so the request degrades to the prose
 * path instead of travelling as an unknown value the backend would reject with
 * a 422 on a request the user did nothing wrong to make.
 */
const KNOWN_CAPABILITIES: readonly CapabilityDirectiveWire['capability'][] = ['person_overview'];

/**
 * The subject bounds the backend ENFORCES, mirrored so the browser can respect
 * them (ADR-184: a limit that is applied must be published to whoever produces
 * the value).
 *
 * Source of truth: `CapabilityDirectiveRequest.subject` in
 * `apps/api/src/domains/agents/api/schemas.py` — grep that name to find both
 * sides. Getting this wrong is not cosmetic: an out-of-bounds subject makes
 * Pydantic reject the WHOLE chat request with a 422, so the user's message
 * would never be sent at all. Dropping the directive instead degrades to the
 * prose path, which is exactly what a hand-edited URL deserves.
 */
const SUBJECT_MIN_LENGTH = 2;
const SUBJECT_MAX_LENGTH = 120;

export interface DeepLinkParams {
  /** `?voice=1` — spotlight push-to-talk on arrival. */
  spotlightVoice: boolean;
  /** `?intent=` — the request to auto-send ('' = none pending). */
  pendingIntent: string;
  /**
   * `?capability=`/`?subject=` — the capability the click invoked (ADR-191),
   * or undefined when the request carries prose only.
   */
  pendingDirective: CapabilityDirectiveWire | undefined;
  /**
   * A resurrected `?intent=` whose iid was already consumed (rule 4,
   * ADR-210) — '' when the arrival is genuine. Exposed so the page can show
   * it in the composer immediately: the persisted draft is read once at
   * mount, BEFORE the arrival effect saves this text, so without this field
   * the replay would visibly do nothing at all.
   */
  replayedIntent: string;
  /**
   * Drop `?intent=`, its directive AND its iid from the URL, and record the
   * iid as consumed. Call it once the request has been acted on — the params
   * are one request and must never outlive each other, or a later prose-only
   * intent would inherit this subject.
   */
  clearIntent: () => void;
}

/**
 * Read the chat deep links; clear the render-time ones now, the intent later.
 *
 * @param saveDraft - Persists `?draft=` before it is cleared, so a refresh right
 *   after arriving keeps the prefill (ChatInput never signals its initial
 *   value, so the URL is the only place it could come from).
 * @returns The live flags for this render, plus the intent's own eraser.
 */
export function useDeepLinkParams(saveDraft: (text: string) => void): DeepLinkParams {
  const searchParams = useSearchParams();

  /**
   * Rewrite the URL without the named params (no-op when none are present).
   *
   * `window.history.replaceState`, NOT `router.replace`: the App Router
   * restores the search params of the entry it already holds for a route, so a
   * replace that only removes params is swallowed — measured, and the same
   * mechanism that made a second deep link leave with the first one's URL
   * (ADR-192). The History API is the officially supported way to update the
   * query without a navigation, and Next syncs `useSearchParams` with it, so
   * the latch below still re-arms exactly as before.
   *
   * It reads `window.location`, not `usePathname()`/`useSearchParams()`: the
   * address bar is what a RELOAD will re-execute, so it is the only source of
   * truth that matters here — and it needs no locale reconstruction.
   */
  const drop = useCallback((names: readonly string[]) => {
    const current = new URLSearchParams(window.location.search);
    if (!names.some(name => current.has(name))) return;
    names.forEach(name => current.delete(name));
    const query = current.toString();
    const { pathname: livePath } = window.location;
    window.history.replaceState(null, '', query ? `${livePath}?${query}` : livePath);
  }, []);

  // Rule 4 (ADR-210): an iid already in the consumed ledger marks this URL as
  // a RESURRECTION (omnibox, session restore, router bookkeeping), not a
  // click. Memoized on the iid so the ledger is read once per arrival, not on
  // every streaming re-render — and never at all when no iid is present.
  const intentValue = searchParams?.get('intent') ?? '';
  const intentId = searchParams?.get('iid') ?? '';
  const replayed = useMemo(() => (intentId ? isIntentConsumed(intentId) : false), [intentId]);

  useEffect(() => {
    // `?draft=` and `?voice=` are consumed during RENDER, so they can go as
    // soon as they arrive. `?intent=` must NOT: its consumer waits for auth.
    const draft = searchParams?.get('draft');
    if (draft?.trim()) saveDraft(draft);
    drop(['draft', 'voice']);
    // A replayed intent is consumed HERE, as a draft: persisting the sentence
    // (never the directive — the user did not re-confirm a guaranteed tool
    // call) keeps it across a reload, and dropping the params closes this
    // resurrection. The composer shows it via `replayedIntent` meanwhile.
    if (replayed && intentValue) {
      saveDraft(intentValue);
      drop(['intent', 'capability', 'subject', 'iid']);
    }
  }, [searchParams, drop, saveDraft, replayed, intentValue]);

  const clearIntent = useCallback(() => {
    // Read the iid from the ADDRESS BAR, like `drop`: it is what a replay
    // would re-present, so it is the value the ledger must hold.
    const liveIntentId = new URLSearchParams(window.location.search).get('iid');
    if (liveIntentId) markIntentConsumed(liveIntentId);
    drop(['intent', 'capability', 'subject', 'iid']);
  }, [drop]);

  const capability = searchParams?.get('capability');
  const subject = searchParams?.get('subject')?.trim();
  const known = KNOWN_CAPABILITIES.find(value => value === capability);
  // Memoized on the PRIMITIVES: a fresh object every render would be a new
  // identity in the auto-send effect's dependency list and re-run it on every
  // single render. The latch would still prevent a double send, but a hook
  // that only works because something downstream absorbs the churn is a defect
  // waiting for its next consumer.
  const pendingDirective = useMemo(() => {
    if (!known || !subject || replayed) return undefined;
    if (subject.length < SUBJECT_MIN_LENGTH || subject.length > SUBJECT_MAX_LENGTH) {
      return undefined;
    }
    return { capability: known, subject };
  }, [known, subject, replayed]);

  return {
    spotlightVoice: searchParams?.get('voice') === '1',
    // Never exposed for even one render when replayed: the auto-send effect
    // fires on the value, and an instant of exposure is an execution.
    pendingIntent: replayed ? '' : intentValue,
    pendingDirective,
    replayedIntent: replayed ? intentValue : '',
    clearIntent,
  };
}
