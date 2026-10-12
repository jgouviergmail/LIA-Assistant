import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';

import { useLandingMedia } from '../use-landing-video';
import { useBeatSync } from '../use-beat-sync';

afterEach(() => vi.unstubAllGlobals());

const strict = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;

it('retires pending metadata on unmount and makes only one request in StrictMode', async () => {
  const fetcher = vi.fn(() => new Promise<Response>(() => {}));
  vi.stubGlobal('fetch', fetcher);
  const mounted = renderHook(() => useLandingMedia(), { wrapper: strict });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  const request = fetcher.mock.calls[0] as unknown as [string, RequestInit];
  expect(request[0]).toBe('/api/landing-media');
  expect(request[1].signal?.aborted).toBe(false);
  mounted.unmount();
  expect(request[1].signal?.aborted).toBe(true);
});

it('retires an audible beat request when its player stops', async () => {
  const fetcher = vi.fn(() => new Promise<Response>(() => {}));
  vi.stubGlobal('fetch', fetcher);
  const ref = { current: null };
  const mounted = renderHook(
    ({ playing }) =>
      useBeatSync(ref, {
        rank: 2,
        hasBeats: true,
        muted: false,
        playing,
        reducedMotion: false,
      }),
    { wrapper: strict, initialProps: { playing: true } }
  );
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  const request = fetcher.mock.calls[0] as unknown as [string, RequestInit];
  expect(request[0]).toBe('/api/landing-media/beats?video=2');
  expect(request[1].signal?.aborted).toBe(false);
  act(() => mounted.rerender({ playing: false }));
  expect(request[1].signal?.aborted).toBe(true);
});
