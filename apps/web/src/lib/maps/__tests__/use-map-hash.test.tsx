/**
 * The page's fragment as React state: read on arrival, followed on every
 * change, written by the page without a history entry.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { setMapHash, useMapHash } from '../use-map-hash';

describe('useMapHash', () => {
  afterEach(() => {
    window.history.replaceState(null, '', window.location.pathname);
  });

  it('reads the fragment, decoded, and follows a hashchange', () => {
    window.history.replaceState(null, '', '#f.chat');
    const { result } = renderHook(() => useMapHash());
    expect(result.current).toBe('f.chat');
    act(() => {
      window.history.replaceState(null, '', '#adr-12');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(result.current).toBe('adr-12');
  });

  it('tells its readers when the page writes the fragment, and clears it', () => {
    const { result } = renderHook(() => useMapHash());
    act(() => setMapHash('t.redis'));
    expect(result.current).toBe('t.redis');
    expect(window.location.hash).toBe('#t.redis');
    act(() => setMapHash(null));
    expect(result.current).toBe('');
    expect(window.location.hash).toBe('');
  });

  it('treats a fragment it cannot decode as no address', () => {
    window.history.replaceState(null, '', '#%E0%A4%A');
    const { result } = renderHook(() => useMapHash());
    expect(result.current).toBe('');
  });
});
