/**
 * The landing's media manifest and the descriptor the page receives (ADR-330).
 *
 * The public pages are prebuilt and host-neutral (B03), so the video the
 * landing shows cannot be named at build time: the operator hosts a
 * directory — the renditions, a poster, optionally a beat map — with a
 * `manifest.json` describing it, and names that directory at run time
 * (`LANDING_MEDIA_BASE_URL`). This module is the ONE reading of that file.
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

/** What the operator writes beside the files. */
export const landingMediaManifestSchema = z.object({
  version: z.literal(1),
  poster: fileName,
  renditions: z.array(renditionSchema).min(1).max(12),
  aspectRatio: z.tuple([z.number().positive(), z.number().positive()]).default([16, 9]),
  durationSeconds: z.number().positive().nullable().default(null),
  beats: fileName.nullable().default(null),
  credit: creditSchema.nullable().default(null),
  aiGenerated: z.boolean().default(false),
});

export type LandingMediaManifest = z.infer<typeof landingMediaManifestSchema>;

export interface LandingRendition {
  src: string;
  type: string;
  minWidth?: number;
}

/** What the page receives: absolute URLs, and no file name of the beat map. */
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

/**
 * Validate a manifest and resolve everything it names under `baseUrl`.
 *
 * @throws {ZodError} when the manifest does not have the declared shape.
 * @throws {TypeError} when a file name is not bare (unreachable after parsing,
 *   kept as the single place the rule is written).
 */
export function resolveLandingMedia(manifest: unknown, baseUrl: string): LandingVideoDescriptor {
  const parsed = landingMediaManifestSchema.parse(manifest);
  return {
    poster: resolveMediaFile(baseUrl, parsed.poster),
    renditions: parsed.renditions.map(({ src, type, minWidth }) => ({
      src: resolveMediaFile(baseUrl, src),
      type,
      ...(minWidth === undefined ? {} : { minWidth }),
    })),
    aspectRatio: parsed.aspectRatio,
    durationSeconds: parsed.durationSeconds,
    hasBeats: parsed.beats !== null,
    credit: parsed.credit,
    aiGenerated: parsed.aiGenerated,
  };
}
