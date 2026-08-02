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
