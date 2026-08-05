/**
 * useDeepLinkParams — the chat's one-shot deep links.
 *
 * The oracle that matters is the one production wrote on 2026-08-01: a 360°
 * recap on one person, then on another, then on a third executed the FIRST
 * one's sentence all three times. Three causes, one test each:
 *
 *  - the value was captured at mount, so a new query on the SAME route (which
 *    does not remount the page) kept the previous request;
 *  - the strip went through `router.replace`, which the App Router swallows
 *    when it only removes params — it restores the search params of the entry
 *    it already holds (ADR-192), so the deep link outlived its consumption and
 *    a reload re-executed it;
 *  - the intent was cleared on ARRIVAL, which raced auth resolution.
 *
 * The URL here is the REAL one — `window.location`, driven through the History
 * API exactly as the hook writes it. A mocked `useSearchParams` alone would
 * test a source the hook no longer strips from.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const { params } = vi.hoisted(() => ({ params: { current: new URLSearchParams() } }));

vi.mock('next/navigation', () => ({
  useSearchParams: () => params.current,
}));

import { useDeepLinkParams } from '../useDeepLinkParams';
import { isIntentConsumed, markIntentConsumed } from '@/lib/intent-replay-guard';

const PATH = '/fr/dashboard/chat';

/** Put the browser AND the router's view on the same query. */
function at(query: string) {
  params.current = new URLSearchParams(query);
  window.history.replaceState(null, '', query ? `${PATH}?${query}` : PATH);
}

/** What the address bar holds — the only thing a reload will re-execute. */
function url(): string {
  return `${window.location.pathname}${window.location.search}`;
}

beforeEach(() => {
  at('');
  window.localStorage.clear();
});

describe('useDeepLinkParams', () => {
  it('reads the intent of the CURRENT url, not the one it mounted with', () => {
    at('intent=Point%20360%C2%B0%20sur%20A');
    const { result, rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(result.current.pendingIntent).toBe('Point 360° sur A');

    // A second deep link to the same route: the query changes, the page does
    // NOT remount. A mount-captured value would still read "A" here.
    at('intent=Point%20360%C2%B0%20sur%20B');
    rerender();
    expect(result.current.pendingIntent).toBe('Point 360° sur B');
  });

  it('KEEPS the intent on arrival — its consumer waits for auth', () => {
    // Production, 2026-08-01 06:30: clearing it at mount won the race against
    // auth resolution and the request evaporated. The scope PUT succeeded five
    // times while the chat received nothing.
    at('intent=go&voice=1');
    renderHook(() => useDeepLinkParams(vi.fn()));
    expect(url()).toBe(`${PATH}?intent=go`);
  });

  it('clears the intent only when the consumer says it is done', () => {
    at('intent=go');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(url()).toBe(`${PATH}?intent=go`); // nothing else to strip

    result.current.clearIntent();
    expect(url()).toBe(PATH);
  });

  it('really leaves the address bar, so a RELOAD cannot re-execute it', () => {
    // The defect ADR-192 explained: `router.replace` reported success and the
    // param stayed. Asserting the call would have passed; asserting the URL is
    // what catches it.
    at('intent=Point%20360%C2%B0&capability=person_overview&subject=Marie');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    result.current.clearIntent();

    expect(url()).toBe(PATH);
    expect(window.location.search).toBe('');
  });

  it('keeps the query parameters it does not own', () => {
    at('intent=go&voice=1&conversation=42');
    const { result, rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(url()).toBe(`${PATH}?intent=go&conversation=42`);

    // The arrival strip landed: React re-renders with the new URL, which is
    // what `clearIntent` must close over.
    params.current = new URLSearchParams('intent=go&conversation=42');
    rerender();
    result.current.clearIntent();
    expect(url()).toBe(`${PATH}?conversation=42`);
  });

  it('persists the draft BEFORE clearing it', () => {
    at('draft=bonjour');
    const saveDraft = vi.fn();
    renderHook(() => useDeepLinkParams(saveDraft));
    expect(saveDraft).toHaveBeenCalledWith('bonjour');
    expect(url()).toBe(PATH);
  });

  it('does not touch the url when there is nothing to consume', () => {
    at('conversation=42');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(url()).toBe(`${PATH}?conversation=42`);
    expect(result.current.pendingIntent).toBe('');
    expect(result.current.spotlightVoice).toBe(false);
  });

  it('cannot loop: with nothing left to clear the effect is a no-op', () => {
    at('voice=1');
    const { rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(url()).toBe(PATH);

    // A second pass over an already-clean URL must not write history again —
    // a replaceState loop would make the page unusable.
    const spy = vi.spyOn(window.history, 'replaceState');
    params.current = new URLSearchParams('');
    rerender();
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it('reports the push-to-talk spotlight', () => {
    at('voice=1');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(result.current.spotlightVoice).toBe(true);
  });
});

/**
 * The FOURTH failure mode (ADR-210), paid for in production on 2026-08-05: a
 * `?intent=` URL is a replayable carrier. The real navigation of ADR-192 makes
 * it a first-class browser-history VISIT, and `replaceState` cleans the
 * session entry, never the visit database — so the omnibox, a most-visited
 * tile, a session restore or the router's own entry bookkeeping can resurrect
 * it and re-execute the request. The one-shot `iid` + consumed ledger makes
 * consumption idempotent whatever resurrects the URL.
 */
describe('useDeepLinkParams — intent replay (ADR-210)', () => {
  it('exposes a FRESH intent and consumes its iid on clearIntent', () => {
    at('intent=go&iid=click-1');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    expect(result.current.pendingIntent).toBe('go');
    expect(result.current.replayedIntent).toBe('');
    expect(isIntentConsumed('click-1')).toBe(false); // not before consumption

    result.current.clearIntent();

    expect(isIntentConsumed('click-1')).toBe(true);
    expect(url()).toBe(PATH); // iid stripped WITH the intent
  });

  it('a REPLAYED iid never becomes a pending intent — it degrades to a draft', () => {
    markIntentConsumed('click-1');
    at(
      'intent=Pr%C3%A9pare%20une%20r%C3%A9ponse&iid=click-1&capability=person_overview&subject=Marie'
    );
    const saveDraft = vi.fn();
    const { result } = renderHook(() => useDeepLinkParams(saveDraft));

    // Never exposed for sending — not even for one render (the auto-send
    // effect fires on the value, an instant of exposure is an execution).
    expect(result.current.pendingIntent).toBe('');
    expect(result.current.pendingDirective).toBeUndefined();
    // Degraded to a visible draft: "saved, never silently dropped".
    expect(result.current.replayedIntent).toBe('Prépare une réponse');
    expect(saveDraft).toHaveBeenCalledWith('Prépare une réponse');
    // The whole request leaves the URL in one breath, directive included.
    expect(url()).toBe(PATH);
  });

  it('the draft of a replay keeps the SENTENCE, never the directive', () => {
    markIntentConsumed('click-1');
    at('intent=go&iid=click-1&capability=person_overview&subject=Marie');
    const saveDraft = vi.fn();
    renderHook(() => useDeepLinkParams(saveDraft));

    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft).toHaveBeenCalledWith('go');
  });

  it('an intent WITHOUT iid keeps the legacy contract — auto-send on every click', () => {
    // Backend-emitted links ("Run it now" on a proposed scheduled action) are
    // durable and deliberately replayable: each CLICK is a consent. They carry
    // no iid, so the ledger never blocks them.
    at('intent=go');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(result.current.pendingIntent).toBe('go');

    result.current.clearIntent();
    expect(url()).toBe(PATH);

    // The same URL arrives again (second click on the notification link).
    at('intent=go');
    const again = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(again.result.current.pendingIntent).toBe('go');
  });

  it('two DIFFERENT clicks on the same action are two executions', () => {
    at('intent=go&iid=click-1');
    const first = renderHook(() => useDeepLinkParams(vi.fn()));
    first.result.current.clearIntent();

    // Same sentence, new click, new iid: must be exposed again.
    at('intent=go&iid=click-2');
    const second = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(second.result.current.pendingIntent).toBe('go');
  });

  it('replay handling cannot loop: a second pass over the cleaned URL is a no-op', () => {
    markIntentConsumed('click-1');
    at('intent=go&iid=click-1');
    const { rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(url()).toBe(PATH);

    const spy = vi.spyOn(window.history, 'replaceState');
    params.current = new URLSearchParams('');
    rerender();
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
