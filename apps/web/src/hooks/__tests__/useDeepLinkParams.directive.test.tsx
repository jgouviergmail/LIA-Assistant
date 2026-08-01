/**
 * `?capability=`/`?subject=` — the click's certainty, carried as data.
 *
 * Prose alone cannot carry a guarantee: measured in production on 2026-08-01,
 * the 360° tool scored 0.853 — the best of the whole catalogue — and the plan
 * called the generic mail tool instead (ADR-191). The sentence stays what the
 * user reads; the directive is what the backend guarantees to run.
 *
 * The rules that matter here are about LIFETIME. The directive and its intent
 * are ONE request: they arrive together, they are cleared together, and a
 * directive that outlived its sentence would silently attach this person to the
 * next, unrelated deep link.
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

describe('useDeepLinkParams — capability directive', () => {
  it('reads the capability and its subject', () => {
    at('intent=Point%20360&capability=person_overview&subject=Paul%20Martin');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    expect(result.current.pendingDirective).toEqual({
      capability: 'person_overview',
      subject: 'Paul Martin',
    });
  });

  it('keeps the same object identity across renders', () => {
    // The auto-send effect lists it as a dependency: a fresh object every
    // render would re-run that effect on every single render. The latch would
    // still prevent a double send, but a hook that only works because
    // something downstream absorbs the churn is a defect waiting for its next
    // consumer.
    at('intent=go&capability=person_overview&subject=Marie');
    const { result, rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    const first = result.current.pendingDirective;

    rerender();

    expect(result.current.pendingDirective).toBe(first);
  });

  it('follows the subject when the deep link changes person', () => {
    at('intent=A&capability=person_overview&subject=Marie%20Dupont');
    const { result, rerender } = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(result.current.pendingDirective?.subject).toBe('Marie Dupont');

    // Same route, new query — the page does NOT remount (the very trap that
    // sent one person's sentence three times in production).
    at('intent=B&capability=person_overview&subject=Paul%20Martin');
    rerender();

    expect(result.current.pendingDirective?.subject).toBe('Paul Martin');
  });

  it('clears the directive together with the intent', () => {
    at('intent=go&capability=person_overview&subject=Marie');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    result.current.clearIntent();

    expect(replace).toHaveBeenLastCalledWith('/fr/dashboard/chat', { scroll: false });
  });

  it('does not survive its sentence', () => {
    // A directive left in the URL would attach THIS person to the next intent.
    at('intent=go&capability=person_overview&subject=Marie&conversation=42');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    result.current.clearIntent();

    const href = String(replace.mock.calls.at(-1)?.[0]);
    expect(href).not.toContain('capability');
    expect(href).not.toContain('subject');
    expect(href).toContain('conversation=42');
  });

  it('ignores a capability nobody implements', () => {
    // Hand-edited URL. Degrading to the prose path beats sending a value the
    // backend would 422 on a request the user did nothing wrong to make.
    at('intent=go&capability=delete_everything&subject=Marie');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    expect(result.current.pendingDirective).toBeUndefined();
    expect(result.current.pendingIntent).toBe('go');
  });

  it('ignores a capability with no subject', () => {
    at('intent=go&capability=person_overview&subject=%20%20');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    expect(result.current.pendingDirective).toBeUndefined();
  });

  it('drops a subject the backend would reject rather than lose the message', () => {
    // `subject` is bounded 2..120 server-side. An out-of-bounds value makes
    // Pydantic reject the WHOLE chat request with a 422, so the user's message
    // would never be sent at all. Degrading to the prose path is the honest
    // failure — and the only one a hand-edited URL deserves.
    at('intent=go&capability=person_overview&subject=A');
    const short = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(short.result.current.pendingDirective).toBeUndefined();
    expect(short.result.current.pendingIntent).toBe('go');

    at(`intent=go&capability=person_overview&subject=${'x'.repeat(121)}`);
    const long = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(long.result.current.pendingDirective).toBeUndefined();
  });

  it('accepts the bounds themselves', () => {
    at(`intent=go&capability=person_overview&subject=${'x'.repeat(120)}`);
    const max = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(max.result.current.pendingDirective?.subject).toHaveLength(120);

    at('intent=go&capability=person_overview&subject=Li');
    const min = renderHook(() => useDeepLinkParams(vi.fn()));
    expect(min.result.current.pendingDirective?.subject).toBe('Li');
  });

  it('leaves a prose-only intent without a directive', () => {
    at('intent=Quelle%20heure%20est-il');
    const { result } = renderHook(() => useDeepLinkParams(vi.fn()));

    expect(result.current.pendingDirective).toBeUndefined();
    expect(result.current.pendingIntent).toBe('Quelle heure est-il');
  });

  it('does not clear the directive on arrival', () => {
    // Same race as `?intent=`: the auto-send waits for auth, and a directive
    // cleared at mount evaporates with it.
    at('intent=go&capability=person_overview&subject=Marie&voice=1');
    renderHook(() => useDeepLinkParams(vi.fn()));

    const href = String(replace.mock.calls.at(-1)?.[0]);
    expect(href).toContain('capability=person_overview');
    expect(href).toContain('subject=Marie');
  });
});
