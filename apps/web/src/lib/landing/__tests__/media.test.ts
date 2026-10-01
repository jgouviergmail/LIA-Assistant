/**
 * The landing's media manifest is the operator's file, fetched at run time
 * (ADR-330): everything it names is resolved UNDER its own directory and
 * nothing else, and what the page receives is a descriptor of absolute URLs,
 * never the manifest's words.
 */

import { describe, expect, it } from 'vitest';

import { resolveLandingMedia, resolveMediaFile } from '../media';

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

describe('resolveLandingMedia', () => {
  it('turns a valid manifest into absolute URLs and keeps the credit', () => {
    const video = resolveLandingMedia(MANIFEST, BASE);
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
    const video = resolveLandingMedia(
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
      resolveLandingMedia({ ...MANIFEST, credit: { label: 'x', url: 'javascript:alert(1)' } }, BASE)
    ).toThrow();
    expect(() =>
      resolveLandingMedia({ ...MANIFEST, credit: { label: 'x', url: 'http://x.com/a' } }, BASE)
    ).toThrow();
  });

  it('refuses a file name that leaves the directory, wherever it appears', () => {
    expect(() => resolveLandingMedia({ ...MANIFEST, poster: '../p.webp' }, BASE)).toThrow();
    expect(() =>
      resolveLandingMedia(
        { ...MANIFEST, renditions: [{ src: 'https://evil.example/v.mp4', type: 'video/mp4' }] },
        BASE
      )
    ).toThrow();
    expect(() => resolveLandingMedia({ ...MANIFEST, beats: '/etc/passwd' }, BASE)).toThrow();
  });

  it('refuses an unknown version, an empty rendition list and a non-object', () => {
    expect(() => resolveLandingMedia({ ...MANIFEST, version: 2 }, BASE)).toThrow();
    expect(() => resolveLandingMedia({ ...MANIFEST, renditions: [] }, BASE)).toThrow();
    expect(() => resolveLandingMedia('nope', BASE)).toThrow();
    expect(() => resolveLandingMedia(null, BASE)).toThrow();
  });
});
