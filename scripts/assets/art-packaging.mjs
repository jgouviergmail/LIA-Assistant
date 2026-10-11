/** Offline, bounded artwork encoding and atomic immutable publication. */
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { lstat, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
export const isMain = url =>
  process.argv[1] && url === pathToFileURL(resolve(process.argv[1])).href;

function ffmpeg(args, maxBuffer = 256 * 1024) {
  const result = spawnSync(
    'ffmpeg',
    ['-hide_banner', '-loglevel', 'error', '-threads', '2', '-filter_threads', '1', ...args],
    {
      windowsHide: true,
      maxBuffer,
      timeout: 120_000,
    }
  );
  if (result.error || result.status !== 0)
    throw new Error(`Artwork encoding failed: ${result.error?.message ?? String(result.stderr)}`);
  return result.stdout;
}

function assertVisibleAlpha(pixels, requireAlpha = true) {
  let transparent = false;
  let visible = false;
  for (let index = 3; index < pixels.length; index += 4) {
    transparent ||= pixels[index] === 0;
    visible ||= pixels[index] > 0;
  }
  if ((requireAlpha && !transparent) || !visible)
    throw new Error('Artwork must contain real transparent and visible pixels');
}

function webpCanvas(bytes) {
  if (
    bytes.length < 20 ||
    bytes.toString('ascii', 0, 4) !== 'RIFF' ||
    bytes.toString('ascii', 8, 12) !== 'WEBP' ||
    bytes.readUInt32LE(4) + 8 !== bytes.length
  )
    throw new Error('Invalid WebP envelope');
  let width = 0;
  let height = 0;
  let alpha = false;
  for (let offset = 12; offset + 8 <= bytes.length; ) {
    const key = bytes.toString('ascii', offset, offset + 4);
    const length = bytes.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (start + length > bytes.length) throw new Error('Truncated WebP chunk');
    if (key === 'ANIM' || key === 'ANMF') throw new Error('Artwork delivery must be a still');
    if (key === 'VP8X') {
      if (length < 10 || bytes[start] & 2) throw new Error('Invalid or animated WebP canvas');
      width = bytes.readUIntLE(start + 4, 3) + 1;
      height = bytes.readUIntLE(start + 7, 3) + 1;
      alpha = Boolean(bytes[start] & 0x10);
    }
    if (key === 'VP8L' && !width) {
      if (length < 5 || bytes[start] !== 0x2f) throw new Error('Invalid lossless WebP canvas');
      const packed = bytes.readUInt32LE(start + 1);
      width = (packed & 0x3fff) + 1;
      height = ((packed >>> 14) & 0x3fff) + 1;
      alpha = Boolean((packed >>> 28) & 1);
    }
    if (key === 'VP8 ' && !width) {
      if (length < 10 || bytes.toString('hex', start + 3, start + 6) !== '9d012a')
        throw new Error('Invalid lossy WebP canvas');
      width = bytes.readUInt16LE(start + 6) & 0x3fff;
      height = bytes.readUInt16LE(start + 8) & 0x3fff;
    }
    offset = start + length + (length % 2);
  }
  return { width, height, alpha };
}

export async function encodeArtwork(
  input,
  destination,
  width,
  height,
  budget,
  requireAlpha = true
) {
  if (
    typeof input.source !== 'string' ||
    !input.source ||
    typeof input.prompt !== 'string' ||
    !input.prompt
  )
    throw new Error('Artwork source and exact authoring prompt are required');
  // Padding alone must not let an opaque backdrop pass. This bounded sample
  // changes neither the published pixels nor the author's artwork.
  assertVisibleAlpha(
    ffmpeg([
      '-i',
      resolve(input.source),
      '-frames:v',
      '1',
      '-vf',
      'scale=64:64:force_original_aspect_ratio=decrease:flags=neighbor',
      '-f',
      'rawvideo',
      '-pix_fmt',
      'rgba',
      'pipe:1',
    ]),
    requireAlpha
  );
  ffmpeg([
    '-y',
    '-i',
    resolve(input.source),
    '-frames:v',
    '1',
    '-vf',
    `scale=${width}:${height}:force_original_aspect_ratio=decrease:flags=lanczos,format=rgba,pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2:color=black@0`,
    '-c:v',
    'libwebp',
    '-quality',
    '94',
    '-compression_level',
    '6',
    '-preset',
    'picture',
    '-pix_fmt',
    'yuva420p',
    destination,
  ]);
  const bytes = await readFile(destination);
  if (bytes.length > budget)
    throw new Error(`Artwork exceeds delivery budget: ${basename(destination)}`);
  const canvas = webpCanvas(bytes);
  if (canvas.width !== width || canvas.height !== height || (requireAlpha && !canvas.alpha))
    throw new Error('WebP delivery has the wrong dimensions or transparency');
  const pixels = ffmpeg(
    ['-i', destination, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgba', 'pipe:1'],
    width * height * 4 + 64 * 1024
  );
  if (pixels.length !== width * height * 4) throw new Error('Incomplete WebP pixel decode');
  assertVisibleAlpha(pixels, requireAlpha);
  return {
    record: { width, height, bytes: bytes.length, sha256: sha256(bytes) },
    artwork: {
      file: basename(input.source),
      sha256: sha256(await readFile(input.source)),
      prompt_sha256: sha256(input.prompt),
    },
  };
}

async function assertUnpublished(directory) {
  try {
    await lstat(directory);
  } catch (error) {
    if (error.code === 'ENOENT') return;
    throw error;
  }
  throw new Error(`Immutable artwork version already exists: ${directory}`);
}

export async function publishImmutablePack(directory, budget, build) {
  const destination = resolve(directory);
  const parent = dirname(destination);
  await assertUnpublished(destination);
  await mkdir(parent, { recursive: true });
  const prefix = join(parent, `.lia-art-${basename(destination)}-`);
  const stage = await mkdtemp(prefix);
  try {
    const manifest = await build(stage);
    const text = `${JSON.stringify(manifest, null, 2)}\n`;
    if (manifest.total_bytes + Buffer.byteLength(text) > budget)
      throw new Error('Artwork pack exceeds delivery budget');
    await writeFile(join(stage, 'manifest.json'), text, 'utf8');
    await assertUnpublished(destination);
    await rename(stage, destination);
    return manifest;
  } finally {
    // Resolve and check the exact generated stage before recursive cleanup.
    // Published versions and paths supplied by artwork records are excluded.
    if (dirname(resolve(stage)) !== parent || !resolve(stage).startsWith(prefix))
      throw new Error('Unsafe artwork staging cleanup');
    await rm(stage, { recursive: true, force: true });
  }
}
