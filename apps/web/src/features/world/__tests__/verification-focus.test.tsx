import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useWorldVerificationFocus } from '../useWorldVerificationFocus';
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});
it('a fast read does not leave a stale field bookmark for the next verification', async () => {
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation(callback => {
    frames.push(callback);
    return frames.length;
  });
  vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {});
  vi.spyOn(document, 'hasFocus').mockReturnValue(true);
  const dialog = document.createElement('section');
  dialog.setAttribute('role', 'dialog');
  const previous = document.createElement('input');
  const current = document.createElement('input');
  const resumed = document.createElement('button');
  dialog.append(resumed, previous, current);
  document.body.append(dialog);
  previous.focus();
  const refetch = vi.fn(async () => {});
  const { result, rerender } = renderHook(
    ({ hidden }) => useWorldVerificationFocus(hidden, false, refetch),
    { initialProps: { hidden: false } }
  );
  await act(async () => result.current());
  act(() => {
    for (const frame of frames.splice(0)) frame(0);
  });
  current.focus();
  const response = Promise.withResolvers<void>();
  refetch.mockImplementationOnce(() => response.promise);
  let verifying = Promise.resolve();
  act(() => {
    verifying = result.current();
  });
  rerender({ hidden: true });
  await act(async () => {
    response.resolve();
    await verifying;
  });
  rerender({ hidden: false });
  resumed.focus();
  act(() => {
    for (const frame of frames.splice(0)) frame(0);
  });
  expect(current).toHaveFocus();
});
