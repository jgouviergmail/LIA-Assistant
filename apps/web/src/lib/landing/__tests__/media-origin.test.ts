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
});
