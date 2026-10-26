import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, readPublicAssetResponse } from '../api-client';
afterEach(() => vi.unstubAllGlobals());
it('reads an anonymous same-origin static body without consuming or authenticating it', async () => {
  const response = new Response(new Uint8Array([1, 2, 3]));
  const fetcher = vi.fn(async () => response);
  vi.stubGlobal('fetch', fetcher);
  const signal = new AbortController().signal;
  expect(await readPublicAssetResponse('/world/audio/v1/rain.mp3?v=2', signal)).toBe(response);
  expect(response.bodyUsed).toBe(false);
  expect(fetcher).toHaveBeenCalledWith(
    '/world/audio/v1/rain.mp3?v=2',
    expect.objectContaining({
      credentials: 'omit',
      cache: 'force-cache',
      redirect: 'error',
      signal,
    })
  );
});
it.each([
  'https://other.test/sound.mp3',
  '//other.test/sound.mp3',
  '//other.mp3',
  '///other.mp3',
  '/api/v1/private.mp3',
  '/world/../private.mp3',
  '/world/%2e%2e/private.mp3',
  '/world/audio\\private.mp3',
])('refuses a non-public asset path: %s', async path => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  await expect(readPublicAssetResponse(path, new AbortController().signal)).rejects.toBeInstanceOf(
    TypeError
  );
  expect(fetcher).not.toHaveBeenCalled();
});
it('keeps public 401s typed without ejecting the authenticated application', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(null, { status: 401 }))
  );
  const location = window.location.href;
  await expect(
    readPublicAssetResponse('/world/audio/v1/rain.mp3?v=2', new AbortController().signal)
  ).rejects.toMatchObject({ name: 'ApiError', status: 401 });
  expect(window.location.href).toBe(location);
  expect(new ApiError('asset', 404)).toBeInstanceOf(Error);
});
