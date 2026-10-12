/** Same-origin public configuration never sends a session or invokes auth redirects. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, readPublicUiJson } from '../api-client';

afterEach(() => vi.unstubAllGlobals());

describe('Public UI JSON transport', () => {
  it('uses the declared local route even when the backend has another origin', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ revision: 'demo' })));
    vi.stubGlobal('fetch', fetchMock);
    expect(await readPublicUiJson('/api/runtime-ui')).toEqual({ revision: 'demo' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/runtime-ui',
      expect.objectContaining({
        credentials: 'omit',
        headers: { accept: 'application/json' },
        signal: expect.any(AbortSignal),
      })
    );
  });

  it('returns an HTTP failure without redirecting the visitor to sign in', async () => {
    const location = window.location.href;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 401 }))
    );
    await expect(readPublicUiJson('/api/landing-media')).rejects.toBeInstanceOf(ApiError);
    expect(window.location.href).toBe(location);
  });

  it('keeps the caller cancellation signal effective', async () => {
    const controller = new AbortController();
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, options: RequestInit) => {
        signal = options.signal ?? undefined;
        return new Response('{}');
      })
    );
    await readPublicUiJson('/api/landing-media', { signal: controller.signal });
    controller.abort();
    expect(signal?.aborted).toBe(true);
  });

  it('revalidates browser metadata on the declared explicit refresh route', async () => {
    const fetchMock = vi.fn(async () => new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);
    await readPublicUiJson('/api/landing-media?refresh=1');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/landing-media?refresh=1',
      expect.objectContaining({ cache: 'no-store', credentials: 'omit' })
    );
  });

  it.each([
    '/api/landing-media?refresh=2',
    '/api/landing-media?refresh=1&origin=other',
    'https://other.example/api/landing-media',
  ])('refuses an undeclared public refresh endpoint: %s', async endpoint => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      readPublicUiJson(endpoint as Parameters<typeof readPublicUiJson>[0])
    ).rejects.toBeInstanceOf(TypeError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
