/** Historical public films retained byte-for-byte beside each new delivery.
 * The checked configuration is the authority, never a previous generated export.
 * This module does no downloading, encoding, rendering or publication.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat, readFile, realpath } from 'node:fs/promises';
import path from 'node:path';
import type { LandingMediaManifest } from '../../../apps/web/src/lib/landing/media.ts';
import type { BeatMap } from '../../../apps/web/src/lib/landing/beats-schema.ts';

type Video = Omit<LandingMediaManifest, 'version' | 'next' | 'presentation'>;
interface NativeSchemas {
  landingMediaManifestSchema: { parse(value: unknown): LandingMediaManifest };
  beatMapSchema: { parse(value: unknown): BeatMap };
}
interface PreservedAsset {
  name: string;
  bytes: number;
  sha256: string;
  originalUrl?: string;
}
export interface PreservedPlaylist {
  version: 1;
  videos: { id: string; descriptor: Video }[];
  assets: PreservedAsset[];
  sourceSnapshotSha256?: string;
  sourceManifestUrl?: string;
}
const BARE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const samePath = (left: string, right: string) =>
  process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;

function descriptor(value: unknown, schemas: NativeSchemas): Video {
  assert.ok(value && typeof value === 'object', 'video descriptor is an object');
  const parsed = schemas.landingMediaManifestSchema.parse({ ...value, version: 1, next: [] });
  const { version: _version, next: _next, presentation: _presentation, ...video } = parsed;
  return video;
}

export function validatePreservedPlaylist(raw: unknown, schemas: NativeSchemas): PreservedPlaylist {
  assert.ok(raw && typeof raw === 'object', 'preserved playlist is an object');
  const config = raw as PreservedPlaylist;
  assert.equal(config.version, 1, 'preserved configuration version');
  assert.ok(Array.isArray(config.videos) && config.videos.length > 0, 'preserved videos');
  assert.ok(Array.isArray(config.assets), 'preserved fingerprints');
  const videos = config.videos.map(item => {
    assert.ok(item && typeof item.id === 'string' && BARE_NAME.test(item.id), 'preserved video id');
    const video = descriptor(item.descriptor, schemas);
    assert.ok(
      video.durationSeconds !== null && video.beats !== null,
      'historical timing and beats retained'
    );
    return { id: item.id, descriptor: video };
  });
  assert.equal(new Set(videos.map(item => item.id)).size, videos.length, 'unique preserved ids');
  assert.equal(
    new Set(videos.map(item => item.descriptor.poster)).size,
    videos.length,
    'distinct preserved films'
  );
  const names = new Set(
    videos.flatMap(item => [
      item.descriptor.poster,
      ...item.descriptor.renditions.map(rendition => rendition.src),
      item.descriptor.beats!,
    ])
  );
  for (const asset of config.assets) {
    assert.ok(
      asset && typeof asset.name === 'string' && BARE_NAME.test(asset.name),
      'bare preserved asset name'
    );
    assert.ok(Number.isInteger(asset.bytes) && asset.bytes > 0, 'positive preserved byte count');
    assert.match(asset.sha256, /^[a-f0-9]{64}$/, 'preserved SHA-256');
  }
  assert.equal(
    new Set(config.assets.map(asset => asset.name)).size,
    config.assets.length,
    'unique preserved assets'
  );
  assert.deepEqual(
    config.assets.map(asset => asset.name).sort(),
    [...names].sort(),
    'complete preserved asset fingerprints'
  );
  return { ...config, videos };
}

export async function loadPreservedPlaylist(schemas: NativeSchemas): Promise<PreservedPlaylist> {
  return validatePreservedPlaylist(
    JSON.parse(await readFile(new URL('./preserved-playlist.json', import.meta.url), 'utf8')),
    schemas
  );
}

export function buildMainManifest(
  landing: unknown,
  full: unknown,
  config: PreservedPlaylist,
  schemas: NativeSchemas
): LandingMediaManifest {
  const first = descriptor(landing, schemas);
  const presentation = descriptor(full, schemas);
  return schemas.landingMediaManifestSchema.parse({
    version: 1,
    ...first,
    next: [presentation, ...config.videos.map(item => item.descriptor)],
    presentation,
  });
}

export function validateMainPlaylist(
  raw: unknown,
  landing: unknown,
  full: unknown,
  config: PreservedPlaylist,
  schemas: NativeSchemas
): LandingMediaManifest {
  const parsed = schemas.landingMediaManifestSchema.parse(raw);
  assert.deepEqual(
    parsed,
    buildMainManifest(landing, full, config, schemas),
    'complete ordered public playlist and exclusive full presentation'
  );
  return parsed;
}

async function pinnedFile(directory: string, asset: PreservedAsset) {
  const root = path.resolve(directory);
  const file = path.resolve(root, asset.name);
  assert.ok(
    BARE_NAME.test(asset.name) && samePath(path.dirname(file), root),
    'preserved asset stays in delivery directory'
  );
  const info = await lstat(file);
  assert.ok(info.isFile() && !info.isSymbolicLink(), 'preserved asset is a regular file');
  assert.ok(samePath(await realpath(file), file), 'preserved asset is a physical file');
  assert.equal(info.size, asset.bytes, `preserved byte count: ${asset.name}`);
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  const sha256 = hash.digest('hex');
  assert.equal(sha256, asset.sha256, `preserved byte checksum: ${asset.name}`);
  return { file: asset.name, bytes: info.size, sha256 };
}

export async function verifyPreservedAssets(
  config: PreservedPlaylist,
  directory: string,
  schemas: NativeSchemas
) {
  const info = await lstat(directory);
  assert.ok(info.isDirectory() && !info.isSymbolicLink(), 'physical preserved delivery root');
  assert.ok(
    samePath(await realpath(directory), path.resolve(directory)),
    'preserved delivery root resolves exactly'
  );
  const checked = new Map<string, Awaited<ReturnType<typeof pinnedFile>>>();
  for (const asset of config.assets) checked.set(asset.name, await pinnedFile(directory, asset));
  const records = [];
  for (const item of config.videos) {
    const video = item.descriptor;
    const beats = schemas.beatMapSchema.parse(
      JSON.parse(await readFile(path.join(directory, video.beats!), 'utf8'))
    );
    assert.ok(
      beats.beats.length > 0 && beats.beats.every(([ms]) => ms < video.durationSeconds! * 1000),
      'preserved beats stay within the original film'
    );
    const names = [video.poster, ...video.renditions.map(rendition => rendition.src), video.beats!];
    records.push({
      name: item.id,
      descriptor: video,
      provenance: 'preserved-original-bytes',
      assets: names.map(name => checked.get(name)!),
      beatCount: beats.beats.length,
    });
  }
  return { records, assetCount: checked.size };
}
