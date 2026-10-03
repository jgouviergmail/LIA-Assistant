/**
 * The landing's media manifest is the operator's file, fetched at run time
 * (ADR-330): everything it names is resolved UNDER its own directory and
 * nothing else, and what the page receives is a descriptor of absolute URLs,
 * never the manifest's words.
 */

import { describe, expect, it } from 'vitest';

import {
  beatsFileAt,
  LANDING_MEDIA_MAX_NEXT,
  landingMediaManifestSchema,
  resolveLandingPlaylist,
  resolveMediaFile,
} from '../media';

/** The first video of a manifest, as the page receives it. */
function resolveFirst(manifest: unknown, base: string) {
  return resolveLandingPlaylist(manifest, base)[0];
}

const BASE = 'https://media.example.org/lia/landing';

const MANIFEST = {
  version: 1,
  poster: 'clip-abc123-poster.webp',
  renditions: [
    { src: 'clip-abc123-1080p.av1.mp4', type: 'video/mp4; codecs="av01.0.08M.10"', minWidth: 900 },
    { src: 'clip-abc123-1080p.h264.mp4', type: 'video/mp4; codecs="avc1.640028"', minWidth: 900 },
    { src: 'clip-abc123-720p.h264.mp4', type: 'video/mp4; codecs="avc1.64001f"' },
  ],
  aspectRatio: [16, 9],
  durationSeconds: 306.48,
  beats: 'clip-abc123-beats.json',
  credit: { label: '@someone', url: 'https://x.com/someone' },
  aiGenerated: true,
};

describe('resolveMediaFile', () => {
  it('joins a bare file name under the base directory', () => {
    expect(resolveMediaFile(BASE, 'clip.mp4')).toBe(`${BASE}/clip.mp4`);
    expect(resolveMediaFile(`${BASE}/`, 'clip.mp4')).toBe(`${BASE}/clip.mp4`);
  });

  it.each([
    '../clip.mp4',
    '/clip.mp4',
    'https://other.host/clip.mp4',
    'clip.mp4?x=1',
    'a/b.mp4',
    '',
    ' ',
  ])('refuses a name that could leave the directory: %j', name => {
    expect(() => resolveMediaFile(BASE, name)).toThrow();
  });
});

describe('resolveLandingPlaylist — the first video', () => {
  it('turns a valid manifest into absolute URLs and keeps the credit', () => {
    const video = resolveFirst(MANIFEST, BASE);
    expect(video.poster).toBe(`${BASE}/clip-abc123-poster.webp`);
    expect(video.renditions).toEqual([
      {
        src: `${BASE}/clip-abc123-1080p.av1.mp4`,
        type: 'video/mp4; codecs="av01.0.08M.10"',
        minWidth: 900,
      },
      {
        src: `${BASE}/clip-abc123-1080p.h264.mp4`,
        type: 'video/mp4; codecs="avc1.640028"',
        minWidth: 900,
      },
      { src: `${BASE}/clip-abc123-720p.h264.mp4`, type: 'video/mp4; codecs="avc1.64001f"' },
    ]);
    expect(video.aspectRatio).toEqual([16, 9]);
    expect(video.durationSeconds).toBe(306.48);
    expect(video.hasBeats).toBe(true);
    expect(video.credit).toEqual({ label: '@someone', url: 'https://x.com/someone' });
    expect(video.aiGenerated).toBe(true);
  });

  it('defaults what the manifest leaves out', () => {
    const video = resolveFirst(
      { version: 1, poster: 'p.webp', renditions: [{ src: 'v.mp4', type: 'video/mp4' }] },
      BASE
    );
    expect(video.aspectRatio).toEqual([16, 9]);
    expect(video.durationSeconds).toBeNull();
    expect(video.hasBeats).toBe(false);
    expect(video.credit).toBeNull();
    expect(video.aiGenerated).toBe(false);
  });

  it('refuses a credit that is not an https link', () => {
    expect(() =>
      resolveFirst({ ...MANIFEST, credit: { label: 'x', url: 'javascript:alert(1)' } }, BASE)
    ).toThrow();
    expect(() =>
      resolveFirst({ ...MANIFEST, credit: { label: 'x', url: 'http://x.com/a' } }, BASE)
    ).toThrow();
  });

  it('refuses a file name that leaves the directory, wherever it appears', () => {
    expect(() => resolveFirst({ ...MANIFEST, poster: '../p.webp' }, BASE)).toThrow();
    expect(() =>
      resolveFirst(
        { ...MANIFEST, renditions: [{ src: 'https://evil.example/v.mp4', type: 'video/mp4' }] },
        BASE
      )
    ).toThrow();
    expect(() => resolveFirst({ ...MANIFEST, beats: '/etc/passwd' }, BASE)).toThrow();
  });

  it('refuses an unknown version, an empty rendition list and a non-object', () => {
    expect(() => resolveFirst({ ...MANIFEST, version: 2 }, BASE)).toThrow();
    expect(() => resolveFirst({ ...MANIFEST, renditions: [] }, BASE)).toThrow();
    expect(() => resolveFirst('nope', BASE)).toThrow();
    expect(() => resolveFirst(null, BASE)).toThrow();
  });
});

describe('resolveLandingPlaylist — the videos that follow', () => {
  const SECOND = {
    poster: 'second-poster.webp',
    renditions: [{ src: 'second-720p.av1.mp4', type: 'video/mp4; codecs="av01.0.05M.10"' }],
    beats: 'second-beats.json',
    credit: { label: '@other', url: 'https://x.com/other' },
  };

  it('is the first video alone when the manifest names no other', () => {
    expect(resolveLandingPlaylist(MANIFEST, BASE)).toHaveLength(1);
  });

  it('lists every video in playing order, each resolved and defaulted like the first', () => {
    const playlist = resolveLandingPlaylist({ ...MANIFEST, next: [SECOND] }, BASE);
    expect(playlist.map(video => video.poster)).toEqual([
      `${BASE}/clip-abc123-poster.webp`,
      `${BASE}/second-poster.webp`,
    ]);
    expect(playlist[1]).toEqual({
      poster: `${BASE}/second-poster.webp`,
      renditions: [
        { src: `${BASE}/second-720p.av1.mp4`, type: 'video/mp4; codecs="av01.0.05M.10"' },
      ],
      aspectRatio: [16, 9],
      durationSeconds: null,
      hasBeats: true,
      credit: { label: '@other', url: 'https://x.com/other' },
      aiGenerated: false,
    });
  });

  it('holds the next videos to the same rules as the first, and bounds their number', () => {
    expect(() =>
      resolveLandingPlaylist({ ...MANIFEST, next: [{ ...SECOND, poster: '../p.webp' }] }, BASE)
    ).toThrow();
    expect(() =>
      resolveLandingPlaylist(
        { ...MANIFEST, next: [{ ...SECOND, credit: { label: 'x', url: 'http://x.com' } }] },
        BASE
      )
    ).toThrow();
    expect(() =>
      resolveLandingPlaylist({ ...MANIFEST, next: [{ ...SECOND, renditions: [] }] }, BASE)
    ).toThrow();
    const tooMany = Array.from({ length: LANDING_MEDIA_MAX_NEXT + 1 }, () => SECOND);
    expect(() => resolveLandingPlaylist({ ...MANIFEST, next: tooMany }, BASE)).toThrow();
  });

  it('names the beat map of a video by its rank, and none past the list', () => {
    const manifest = landingMediaManifestSchema.parse({
      ...MANIFEST,
      next: [SECOND, { ...SECOND, beats: null }],
    });
    expect(beatsFileAt(manifest, 0)).toBe('clip-abc123-beats.json');
    expect(beatsFileAt(manifest, 1)).toBe('second-beats.json');
    expect(beatsFileAt(manifest, 2)).toBeNull();
    expect(beatsFileAt(manifest, 3)).toBeNull();
  });
});
