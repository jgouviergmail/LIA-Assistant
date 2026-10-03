/**
 * The landing's media manifest and the descriptor the page receives (ADR-330).
 *
 * The public pages are prebuilt and host-neutral (B03), so the video the
 * landing shows cannot be named at build time: the operator hosts a
 * directory — the renditions, a poster, optionally a beat map — with a
 * `manifest.json` describing it, and names that directory at run time
 * (`LANDING_MEDIA_BASE_URL`). This module is the ONE reading of that file.
 *
 * The manifest describes ONE video at its top level and, optionally, the
 * videos that follow it (`next`, in playing order): the landing plays them
 * one after the other and starts over. `next` was ADDED to version 1 rather
 * than opening a version 2, because the file is read at run time by whatever
 * build a deployment runs — a reader that predates `next` drops the unknown
 * key and plays the first video alone, so one directory serves both.
 *
 * Two rules it enforces, because the manifest is the operator's text and the
 * page will put what it says into `<video>` and `<a href>`:
 *   - every file is a BARE NAME, resolved under the manifest's own directory
 *     and nowhere else (no path, no scheme, no query);
 *   - a credit link is https, or there is no credit link.
 * It is pure: the route handler fetches, this resolves, the component draws.
 */

import { z } from '@/lib/zod';

/** A bare file name: no separator, no query, no fragment, no leading dot. */
const FILE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

const fileName = z.string().regex(FILE_NAME, 'a bare file name');

const renditionSchema = z.object({
  src: fileName,
  /** The `type` the browser negotiates on, e.g. `video/mp4; codecs="av01.0.08M.10"`. */
  type: z.string().trim().min(1).max(200),
  /** Offered only to viewports at least this wide (CSS px); absent = every viewport. */
  minWidth: z.number().int().positive().max(10_000).optional(),
});

const creditSchema = z.object({
  label: z.string().trim().min(1).max(80),
  url: z.url({ protocol: /^https$/ }),
});

/** How many videos may follow the first one. */
export const LANDING_MEDIA_MAX_NEXT = 7;

/** One video: the shape of the manifest's top level and of every `next` entry. */
const videoShape = {
  poster: fileName,
  renditions: z.array(renditionSchema).min(1).max(12),
  aspectRatio: z.tuple([z.number().positive(), z.number().positive()]).default([16, 9]),
  durationSeconds: z.number().positive().nullable().default(null),
  beats: fileName.nullable().default(null),
  credit: creditSchema.nullable().default(null),
  aiGenerated: z.boolean().default(false),
};

const landingVideoSchema = z.object(videoShape);

/** What the operator writes beside the files. */
export const landingMediaManifestSchema = z.object({
  version: z.literal(1),
  ...videoShape,
  next: z.array(landingVideoSchema).max(LANDING_MEDIA_MAX_NEXT).default([]),
});

export type LandingMediaManifest = z.infer<typeof landingMediaManifestSchema>;
type LandingVideoEntry = z.infer<typeof landingVideoSchema>;

export interface LandingRendition {
  src: string;
  type: string;
  minWidth?: number;
}

/** What the page receives for one video: absolute URLs, and no file name of the beat map. */
export interface LandingVideoDescriptor {
  poster: string;
  renditions: LandingRendition[];
  aspectRatio: [number, number];
  durationSeconds: number | null;
  hasBeats: boolean;
  credit: { label: string; url: string } | null;
  aiGenerated: boolean;
}

/**
 * The absolute URL of one file of the media directory.
 *
 * @throws {TypeError} when `name` is not a bare file name.
 */
export function resolveMediaFile(baseUrl: string, name: string): string {
  if (!FILE_NAME.test(name)) {
    throw new TypeError('a media file is named by a bare file name');
  }
  return `${baseUrl.replace(/\/+$/, '')}/${name}`;
}

/** The videos of a validated manifest, in playing order: the top level first. */
function entriesOf(manifest: LandingMediaManifest): LandingVideoEntry[] {
  const { version: _version, next, ...first } = manifest;
  return [first, ...next];
}

function resolveVideo(entry: LandingVideoEntry, baseUrl: string): LandingVideoDescriptor {
  return {
    poster: resolveMediaFile(baseUrl, entry.poster),
    renditions: entry.renditions.map(({ src, type, minWidth }) => ({
      src: resolveMediaFile(baseUrl, src),
      type,
      ...(minWidth === undefined ? {} : { minWidth }),
    })),
    aspectRatio: entry.aspectRatio,
    durationSeconds: entry.durationSeconds,
    hasBeats: entry.beats !== null,
    credit: entry.credit,
    aiGenerated: entry.aiGenerated,
  };
}

/**
 * Validate a manifest and resolve everything it names under `baseUrl`: the
 * videos in playing order, never empty.
 *
 * @throws {ZodError} when the manifest does not have the declared shape.
 * @throws {TypeError} when a file name is not bare (unreachable after parsing,
 *   kept as the single place the rule is written).
 */
export function resolveLandingPlaylist(
  manifest: unknown,
  baseUrl: string
): LandingVideoDescriptor[] {
  return entriesOf(landingMediaManifestSchema.parse(manifest)).map(entry =>
    resolveVideo(entry, baseUrl)
  );
}

/**
 * The beat map's file name of the video at `index` in playing order, or
 * `null` when that video has none or there is no such video.
 */
export function beatsFileAt(manifest: LandingMediaManifest, index: number): string | null {
  return entriesOf(manifest)[index]?.beats ?? null;
}
