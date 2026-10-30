/**
 * Every capture a landing gallery shows has its full set of static variants,
 * written from the original that is on disk TODAY.
 *
 * The variants are files, not a runtime resize (`lib/landing/captures.ts`).
 * Two ways for them to rot, and nothing else would notice either: a view added
 * without running `scripts/build-capture-variants.mjs` ships 404s on the rail
 * and the stage; a capture campaign that replaces an original (same name, new
 * picture) leaves the stage showing the OLD picture while the full-screen view
 * shows the new one. The generator records each original's SHA-256, so both
 * are caught here.
 */

import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  allCaptureViews,
  captureOriginalPath,
  captureStageSrcSet,
  captureVariantPath,
  CAPTURE_STAGE_WIDTHS,
  CAPTURE_VARIANT_WIDTHS,
  CAPTURE_VARIANTS_DIRECTORY,
  CAPTURE_VARIANTS_MANIFEST,
} from '../captures';

const PUBLIC_DIR = join(__dirname, '..', '..', '..', '..', 'public');
const onDisk = (publicPath: string): string => join(PUBLIC_DIR, ...publicPath.split('/'));
const REGENERATE = 'run: node apps/web/scripts/build-capture-variants.mjs';

interface VariantsManifest {
  widths: number[];
  sources: Record<string, { original: string; sha256: string }>;
}

// Read at collection (the `source-scan.ts` rule): hashing ~21 MB of originals
// inside a test would measure the host, not the guard.
const MANIFEST: VariantsManifest = JSON.parse(
  readFileSync(onDisk(CAPTURE_VARIANTS_MANIFEST), 'utf8')
);
const VIEWS = allCaptureViews();
const ORIGINAL_HASHES = new Map(
  VIEWS.map(view => {
    const path = onDisk(captureOriginalPath(view));
    const hash = existsSync(path)
      ? createHash('sha256').update(readFileSync(path)).digest('hex')
      : 'missing';
    return [view.file, hash] as const;
  })
);
const VARIANT_FILES = readdirSync(onDisk(CAPTURE_VARIANTS_DIRECTORY));

describe('landing capture variants', () => {
  it('names each capture once, so no two views share a variant set', () => {
    const files = VIEWS.map(view => view.file);
    expect(new Set(files).size).toBe(files.length);
  });

  it('were written at the widths the page reads', () => {
    expect(MANIFEST.widths, REGENERATE).toEqual([...CAPTURE_VARIANT_WIDTHS]);
  });

  it('were written from the originals on disk today', () => {
    const stale = VIEWS.filter(view => {
      const recorded = MANIFEST.sources[view.file];
      return (
        recorded?.original !== captureOriginalPath(view) ||
        recorded.sha256 !== ORIGINAL_HASHES.get(view.file)
      );
    }).map(view => view.file);
    expect(stale, REGENERATE).toEqual([]);
  });

  it('exist for every view at every width, and nothing else is shipped', () => {
    const expected = VIEWS.flatMap(view =>
      CAPTURE_VARIANT_WIDTHS.map(width => captureVariantPath(view.file, width).split('/').pop())
    );
    expect([...VARIANT_FILES].sort(), REGENERATE).toEqual(['manifest.json', ...expected].sort());
    expect(Object.keys(MANIFEST.sources).sort(), REGENERATE).toEqual(
      VIEWS.map(view => view.file).sort()
    );
  });
});

describe('captureStageSrcSet', () => {
  it('announces the width a candidate actually has, each width once', () => {
    // A 1100-px original: the `-1600` file was never enlarged, so it IS 1100 px.
    expect(captureStageSrcSet('maps', 1100, '?v=r')).toBe(
      '/screenshots/variants/maps-640.webp?v=r 640w, ' +
        '/screenshots/variants/maps-1024.webp?v=r 1024w, ' +
        '/screenshots/variants/maps-1600.webp?v=r 1100w'
    );
    // Narrower than two candidates: they are the same picture, listed once.
    expect(captureStageSrcSet('narrow', 900, '')).toBe(
      '/screenshots/variants/narrow-640.webp 640w, /screenshots/variants/narrow-1024.webp 900w'
    );
  });

  it('keeps the declared widths when the campaign records no size', () => {
    const descriptors = captureStageSrcSet('unknown', undefined, '')
      .split(', ')
      .map(candidate => candidate.split(' ')[1]);
    expect(descriptors).toEqual(CAPTURE_STAGE_WIDTHS.map(width => `${width}w`));
  });
});
