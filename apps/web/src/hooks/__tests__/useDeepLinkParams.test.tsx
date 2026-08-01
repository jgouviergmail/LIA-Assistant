/**
 * useDeepLinkParams — the chat's one-shot deep links.
 *
 * The oracle that matters is the one production wrote on 2026-08-01: a 360°
 * recap on one person, then on another, then on a third executed the FIRST
 * one's sentence all three times. Two independent causes, one test each:
 *
 *  - the value was captured at mount, so a new query on the SAME route (which
 *    does not remount the page) kept the previous request;
 *  - the strip went through `window.history.replaceState`, which rewrites the
 *    address bar behind the App Router's back — so the router kept serving the
 *    first `?intent=` even on later arrivals.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const { replace, params } = vi.hoisted(() => ({
  replace: vi.fn(),
  params: { current: new URLSearchParams() },
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => params.current,
  usePathname: () => '/fr/dashboard/chat',
  useRouter: () => ({ replace }),
}));

import { useDeepLinkParams } from '../useDeepLinkParams';

function at(query: string) {
  params.current = new URLSearchParams(query);
}

beforeEach(() => {
  replace.mockReset();
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
    expect(replace).toHaveBeenCalledWith('/fr/dashboard/chat?intent=go', { scroll: false });
  });

  it('clears the intent only when the consumer says it is done', () => {
    at('intent=go');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(replace).not.toHaveBeenCalled(); // nothing else to strip

    result.current.clearIntent();
    expect(replace).toHaveBeenCalledWith('/fr/dashboard/chat', { scroll: false });
  });

  it('keeps the query parameters it does not own', () => {
    at('intent=go&voice=1&conversation=42');
    const { result, rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(replace).toHaveBeenLastCalledWith('/fr/dashboard/chat?intent=go&conversation=42', {
      scroll: false,
    });

    // The arrival strip landed: React re-renders with the new URL, which is
    // what `clearIntent` must close over (mutating the mock without a rerender
    // would test a closure the app never has).
    at('intent=go&conversation=42');
    rerender();
    result.current.clearIntent();
    expect(replace).toHaveBeenLastCalledWith('/fr/dashboard/chat?conversation=42', {
      scroll: false,
    });
  });

  it('persists the draft BEFORE clearing it', () => {
    at('draft=bonjour');
    const saveDraft = vi.fn();
    renderHook(() => useDeepLinkParams(saveDraft));
    expect(saveDraft).toHaveBeenCalledWith('bonjour');
    expect(replace).toHaveBeenCalledWith('/fr/dashboard/chat', { scroll: false });
  });

  it('does not touch the url when there is nothing to consume', () => {
    at('conversation=42');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(replace).not.toHaveBeenCalled();
    expect(result.current.pendingIntent).toBe('');
    expect(result.current.spotlightVoice).toBe(false);
  });

  it('cannot loop: with nothing left to clear the effect is a no-op', () => {
    at('voice=1');
    const { rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(replace).toHaveBeenCalledTimes(1);

    at('');
    rerender();
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it('reports the push-to-talk spotlight', () => {
    at('voice=1');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(result.current.spotlightVoice).toBe(true);
  });
});
