/**
 * The two run-time doors of the landing video (ADR-330): the descriptor the
 * section mounts on, and the beat map it loads when the sound goes on. Both
 * read the operator's manifest through the same cache; neither ever fails
 * the page — "no video" is an answer.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resetLandingMediaCache } from '@/lib/landing/media-origin';

const { GET: getMedia } = await import('./route');
const { GET: getBeats } = await import('./beats/route');

const BASE = 'https://m.example.org/lia/landing';

const MANIFEST = {
  version: 1,
  poster: 'clip-poster.webp',
  renditions: [{ src: 'clip-720p.h264.mp4', type: 'video/mp4; codecs="avc1.64001f"' }],
  beats: 'clip-beats.json',
  credit: { label: '@someone', url: 'https://x.com/someone' },
  aiGenerated: true,
};

const BEATS = {
  version: 1,
  beats: [
    [0, 1, true],
    [464, 0.6, false],
  ],
};

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function fetchByUrl(answers: Record<string, unknown>) {
  return vi.fn(async (url: string) => {
    const body = answers[url];
    return body === undefined ? jsonResponse({ error: 'not found' }, 404) : jsonResponse(body);
  });
}

beforeEach(() => {
  resetLandingMediaCache();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('GET /api/landing-media', () => {
  it('answers "no video" without a configured origin, and never fetches', async () => {
    vi.stubEnv('LANDING_MEDIA_BASE_URL', '');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const res = await getMedia();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ video: null });
    expect(res.headers.get('cache-control')).toContain('max-age=60');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('serves the descriptor with absolute URLs under the configured origin', async () => {
    vi.stubEnv('LANDING_MEDIA_BASE_URL', `${BASE}/`);
    vi.stubGlobal('fetch', fetchByUrl({ [`${BASE}/manifest.json`]: MANIFEST }));

    const res = await getMedia();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      video: {
        poster: `${BASE}/clip-poster.webp`,
        renditions: [
          { src: `${BASE}/clip-720p.h264.mp4`, type: 'video/mp4; codecs="avc1.64001f"' },
        ],
        aspectRatio: [16, 9],
        durationSeconds: null,
        hasBeats: true,
        credit: { label: '@someone', url: 'https://x.com/someone' },
        aiGenerated: true,
      },
    });
    expect(res.headers.get('cache-control')).toContain('max-age=300');
  });

  it('answers "no video" when the origin fails, when the manifest is invalid, and when the variable is malformed', async () => {
    vi.stubEnv('LANDING_MEDIA_BASE_URL', BASE);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'down' }, 503)));
    expect(await (await getMedia()).json()).toEqual({ video: null });

    resetLandingMediaCache();
    vi.stubGlobal(
      'fetch',
      fetchByUrl({ [`${BASE}/manifest.json`]: { version: 1, renditions: [] } })
    );
    expect(await (await getMedia()).json()).toEqual({ video: null });

    vi.stubEnv('LANDING_MEDIA_BASE_URL', 'not a url');
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(await (await getMedia()).json()).toEqual({ video: null });
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});

describe('GET /api/landing-media/beats', () => {
  it('is 404 without a video, and without a beat map', async () => {
    vi.stubEnv('LANDING_MEDIA_BASE_URL', '');
    expect((await getBeats()).status).toBe(404);

    vi.stubEnv('LANDING_MEDIA_BASE_URL', BASE);
    vi.stubGlobal('fetch', fetchByUrl({ [`${BASE}/manifest.json`]: { ...MANIFEST, beats: null } }));
    expect((await getBeats()).status).toBe(404);
  });

  it('serves the validated map named by the manifest, cached like it', async () => {
    vi.stubEnv('LANDING_MEDIA_BASE_URL', BASE);
    const fetchMock = fetchByUrl({
      [`${BASE}/manifest.json`]: MANIFEST,
      [`${BASE}/clip-beats.json`]: BEATS,
    });
    vi.stubGlobal('fetch', fetchMock);

    const res = await getBeats();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(BEATS);
    expect(res.headers.get('cache-control')).toContain('max-age=300');

    await getBeats();
    expect(fetchMock).toHaveBeenCalledTimes(2); // manifest once, beats once
  });

  it('is 404 when the map is not a beat map', async () => {
    vi.stubEnv('LANDING_MEDIA_BASE_URL', BASE);
    vi.stubGlobal(
      'fetch',
      fetchByUrl({
        [`${BASE}/manifest.json`]: MANIFEST,
        [`${BASE}/clip-beats.json`]: {
          version: 1,
          beats: [
            [10, 1, true],
            [5, 1, false],
          ],
        },
      })
    );
    expect((await getBeats()).status).toBe(404);
  });
});
