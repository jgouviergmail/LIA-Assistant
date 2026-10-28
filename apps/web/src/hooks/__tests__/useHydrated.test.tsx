import { act, renderHook } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
import { useHydrated } from '../useHydrated';

function Probe() {
  return <span>{useHydrated() ? 'client' : 'server'}</span>;
}

it('keeps the server snapshot until hydration, then exposes the browser', async () => {
  const container = document.createElement('div');
  container.innerHTML = renderToString(<Probe />);
  expect(container.textContent).toBe('server');
  const recover = vi.fn();
  const root = hydrateRoot(container, <Probe />, { onRecoverableError: recover });
  await act(async () => {});
  expect(container.textContent).toBe('client');
  expect(recover).not.toHaveBeenCalled();
  act(() => root.unmount());
});

it('is already hydrated on a subsequent client mount', () => {
  const { result, rerender } = renderHook(useHydrated);
  expect(result.current).toBe(true);
  rerender();
  expect(result.current).toBe(true);
});
