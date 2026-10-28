import { act, renderHook } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, expect, it, vi } from 'vitest';
import { useMediaQuery } from '../useMediaQuery';

afterEach(() => vi.unstubAllGlobals());

it('follows viewport changes and releases the subscription on unmount', () => {
  let matches = false;
  const listeners = new Set<() => void>();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches,
      addEventListener: (_event: string, callback: () => void) => listeners.add(callback),
      removeEventListener: (_event: string, callback: () => void) => listeners.delete(callback),
    }))
  );
  const { result, unmount } = renderHook(() => useMediaQuery('(min-width: 1024px)'));
  expect(result.current).toBe(false);
  act(() => {
    matches = true;
    listeners.forEach(listener => listener());
  });
  expect(result.current).toBe(true);
  act(() => {
    matches = false;
    listeners.forEach(listener => listener());
  });
  expect(result.current).toBe(false);
  expect(listeners.size).toBe(1);
  unmount();
  expect(listeners.size).toBe(0);
});

it('keeps desktop-only features off on the server even with a wide browser', () => {
  const matchMedia = vi.fn(() => ({ matches: true }));
  vi.stubGlobal('matchMedia', matchMedia);
  function Probe() {
    return <span>{useMediaQuery('(min-width: 1024px)') ? 'desktop' : 'narrow'}</span>;
  }
  expect(renderToString(<Probe />)).toContain('narrow');
  expect(matchMedia).not.toHaveBeenCalled();
});
