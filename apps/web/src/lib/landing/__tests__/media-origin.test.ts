/**
 * The media origin is read at request time and fetched behind a small cache:
 * one fetch per TTL whatever the traffic, a failure remembered briefly, and
 * a slow origin cut at the timeout — the landing never waits for it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  fetchJsonCached,
  LANDING_MEDIA_FETCH_TIMEOUT_MS,
  LANDING_MEDIA_NEGATIVE_TTL_MS,
  LANDING_MEDIA_TTL_MS,
  landingMediaBaseUrl,
  resetLandingMediaCache,
} from '../media-origin';

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

describe('landingMediaBaseUrl', () => {
  it('reads the variable, trims it and drops a trailing slash', () => {
    expect(
      landingMediaBaseUrl({ LANDING_MEDIA_BASE_URL: ' https://m.example.org/lia/landing/ ' })
    ).toBe('https://m.example.org/lia/landing');
  });

  it('answers null when nothing is configured', () => {
    expect(landingMediaBaseUrl({})).toBeNull();
    expect(landingMediaBaseUrl({ LANDING_MEDIA_BASE_URL: '' })).toBeNull();
    expect(landingMediaBaseUrl({ LANDING_MEDIA_BASE_URL: '   ' })).toBeNull();
  });

  it('refuses anything but an absolute http(s) URL, loudly', () => {
    expect(() => landingMediaBaseUrl({ LANDING_MEDIA_BASE_URL: 'media.example.org/lia' })).toThrow(
      TypeError
    );
    expect(() => landingMediaBaseUrl({ LANDING_MEDIA_BASE_URL: 'ftp://m.example.org/x' })).toThrow(
      TypeError
    );
    expect(() =>
      landingMediaBaseUrl({ LANDING_MEDIA_BASE_URL: 'https://m.example.org/x?y=1' })
    ).toThrow(TypeError);
  });
});

describe('fetchJsonCached', () => {
  const parse = (raw: unknown) => {
    if (typeof raw !== 'object' || raw === null || !('ok' in raw)) throw new Error('bad shape');
    return raw as { ok: true };
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-01T10:00:00Z'));
    resetLandingMediaCache();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('fetches once per TTL and hands later callers the same value', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    const first = await fetchJsonCached('https://m.example.org/a.json', parse);
    const second = await fetchJsonCached('https://m.example.org/a.json', parse);
    expect(first).toEqual({ ok: true });
    expect(second).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.setSystemTime(Date.now() + LANDING_MEDIA_TTL_MS + 1);
    await fetchJsonCached('https://m.example.org/a.json', parse);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('asks for JSON, never a stale copy, and cuts the wait at the timeout', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await fetchJsonCached('https://m.example.org/a.json', parse);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.cache).toBe('no-store');
    expect(new Headers(init.headers).get('accept')).toBe('application/json');
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(LANDING_MEDIA_FETCH_TIMEOUT_MS).toBeLessThanOrEqual(3_000);
  });

  it('remembers a failure briefly, then tries again', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: 'down' }, 503))
      .mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toBeNull();
    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.setSystemTime(Date.now() + LANDING_MEDIA_NEGATIVE_TTL_MS + 1);
    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('answers null — and nothing else — when the fetch throws or the body does not parse', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toBeNull();

    resetLandingMediaCache();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ nope: true })));
    expect(await fetchJsonCached('https://m.example.org/b.json', parse)).toBeNull();
  });

  it('recovers immediately from a cached outage on the first explicit refresh', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({}, 503))
      .mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toBeNull();
    expect(await fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true })).toEqual(
      {
        ok: true,
      }
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('replaces a cached old manifest without waiting for its normal TTL', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ok: true, presentation: null }))
      .mockResolvedValue(jsonResponse({ ok: true, presentation: 'full-film.mp4' }));
    vi.stubGlobal('fetch', fetchMock);

    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toEqual({
      ok: true,
      presentation: null,
    });
    expect(await fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true })).toEqual(
      {
        ok: true,
        presentation: 'full-film.mp4',
      }
    );
  });

  it('shares an in-flight origin read across ordinary and forced callers', async () => {
    let resolve!: (value: ReturnType<typeof jsonResponse>) => void;
    const networkResponse = new Promise<ReturnType<typeof jsonResponse>>(done => (resolve = done));
    const fetchMock = vi.fn(() => networkResponse);
    vi.stubGlobal('fetch', fetchMock);
    const requests = [
      fetchJsonCached('https://m.example.org/a.json', parse),
      fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true }),
      fetchJsonCached('https://m.example.org/a.json', parse),
    ];
    resolve(jsonResponse({ ok: true }));
    expect(await Promise.all(requests)).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('bounds repeated explicit refreshes and coalesces callers waiting for the cooldown', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true });

    const requests = Array.from({ length: 8 }, () =>
      fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true })
    );
    let completed = false;
    void Promise.all(requests).then(() => (completed = true));
    await vi.advanceTimersByTimeAsync(4_999);
    expect(completed).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await Promise.all(requests)).toEqual(Array.from({ length: 8 }, () => ({ ok: true })));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('cuts a queued refresh at the origin timeout and shares the failure with its waiters', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({}, 503))
      .mockImplementation(
        (_url: string, options: RequestInit) =>
          new Promise((_resolve, reject) => {
            options.signal?.addEventListener(
              'abort',
              () => reject(new DOMException('Timeout', 'AbortError')),
              { once: true }
            );
          })
      );
    vi.stubGlobal('fetch', fetchMock);
    expect(
      await fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true })
    ).toBeNull();
    const first = fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true });
    const second = fetchJsonCached('https://m.example.org/a.json', parse, { refresh: true });
    await vi.advanceTimersByTimeAsync(5_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3_000);
    expect(await Promise.all([first, second])).toEqual([null, null]);
    expect(vi.getTimerCount()).toBe(0);
    expect(await fetchJsonCached('https://m.example.org/a.json', parse)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
