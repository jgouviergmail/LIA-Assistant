import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { encodeArtwork, publishImmutablePack } from '../art-packaging.mjs';
import { publishCompanionArt } from '../package_companion_art.mjs';
import { publishContextArt, CONTEXT_ART_SIZES } from '../package_context_art.mjs';

let directory;
let transparent;
let opaque;
before(async () => {
  directory = await mkdtemp(join(tmpdir(), 'lia-art-package-'));
  transparent = join(directory, 'transparent.png');
  opaque = join(directory, 'opaque.png');
  for (const [source, alpha] of [
    [transparent, true],
    [opaque, false],
  ]) {
    const pixels = Buffer.alloc(12 * 6 * 4);
    for (let y = 0; y < 6; y++)
      for (let x = 0; x < 12; x++) {
        const i = (y * 12 + x) * 4;
        pixels[i] = 210;
        pixels[i + 1] = 80;
        pixels[i + 2] = 100;
        pixels[i + 3] = alpha && (x === 0 || y === 0 || x === 11 || y === 5) ? 0 : 255;
      }
    const result = spawnSync(
      'ffmpeg',
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-f',
        'rawvideo',
        '-pixel_format',
        'rgba',
        '-video_size',
        '12x6',
        '-i',
        'pipe:0',
        '-frames:v',
        '1',
        source,
      ],
      { input: pixels, windowsHide: true }
    );
    assert.equal(result.status, 0, String(result.stderr));
  }
});
after(async () => {
  const absolute = resolve(directory);
  assert.equal(dirname(absolute), resolve(tmpdir()));
  assert.ok(absolute.startsWith(join(resolve(tmpdir()), 'lia-art-package-')));
  await rm(absolute, { recursive: true, force: true });
});

const bodyInputs = source =>
  ['female', 'male'].map(variant => ({
    character: 'test-person',
    variant,
    version: 1,
    source,
    prompt: 'An original fixture',
  }));

test('validates the complete pair before exposing a public version', async () => {
  const output = join(directory, 'failure');
  const inputs = bodyInputs(transparent);
  inputs[1].source = join(directory, 'missing.png');
  await assert.rejects(publishCompanionArt(inputs, output), /encoding failed/i);
  await assert.rejects(readdir(join(output, 'test-person', 'v1')), { code: 'ENOENT' });
  assert.deepEqual(await readdir(join(output, 'test-person')), []);
});

test('publishes one complete pair and refuses to change its bytes afterwards', async () => {
  const output = join(directory, 'immutable');
  await publishCompanionArt(bodyInputs(transparent), output);
  const version = join(output, 'test-person', 'v1');
  const before = await readFile(join(version, 'female', 'body.webp'));
  const manifest = JSON.parse(await readFile(join(version, 'manifest.json'), 'utf8'));
  assert.deepEqual((await readdir(version)).sort(), ['female', 'male', 'manifest.json']);
  assert.equal(manifest.assets['female/body'].size, 192);
  assert.equal(manifest.assets['female/body'].bytes, before.length);
  assert.equal(
    manifest.assets['female/body'].sha256,
    createHash('sha256').update(before).digest('hex')
  );
  const decoded = spawnSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      join(version, 'female', 'body.webp'),
      '-frames:v',
      '1',
      '-f',
      'rawvideo',
      '-pix_fmt',
      'rgba',
      'pipe:1',
    ],
    { windowsHide: true }
  );
  assert.equal(decoded.status, 0, String(decoded.stderr));
  let minX = 192,
    minY = 192,
    maxX = -1,
    maxY = -1;
  for (let y = 0; y < 192; y++)
    for (let x = 0; x < 192; x++) {
      if (decoded.stdout[(y * 192 + x) * 4 + 3] < 128) continue;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }
  assert.ok(
    maxX - minX > (maxY - minY) * 2,
    'Rectangular authoring must retain its aspect inside the square canvas'
  );
  await assert.rejects(
    publishCompanionArt(bodyInputs(opaque), output),
    /already exists|immutable/i
  );
  assert.deepEqual(await readFile(join(version, 'female', 'body.webp')), before);
});

test('rejects an opaque source rather than adding padding that conceals its opaque backdrop', async () => {
  const output = join(directory, 'opaque');
  await assert.rejects(publishCompanionArt(bodyInputs(opaque), output), /transparen/i);
  await assert.rejects(readdir(join(output, 'test-person', 'v1')), { code: 'ENOENT' });
});

test('an explicitly opaque knit material retains opacity and its power-of-two delivery dimensions', async () => {
  const target = join(directory, 'knit.webp');
  const result = await encodeArtwork(
    { source: opaque, prompt: 'Opaque knitted material' },
    target,
    128,
    64,
    16 * 1024,
    false
  );
  assert.deepEqual([result.record.width, result.record.height], [128, 64]);
  const decoded = spawnSync(
    'ffmpeg',
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      target,
      '-frames:v',
      '1',
      '-f',
      'rawvideo',
      '-pix_fmt',
      'rgba',
      'pipe:1',
    ],
    { windowsHide: true }
  );
  assert.equal(decoded.status, 0, String(decoded.stderr));
  assert.equal(decoded.stdout.length, 128 * 64 * 4);
  for (let i = 3; i < decoded.stdout.length; i += 4) assert.equal(decoded.stdout[i], 255);
});

test('publishes all ten props at their requested aspect and shares the immutable complete-pack contract', async () => {
  const output = join(directory, 'context', 'v1');
  const inputs = Object.entries(CONTEXT_ART_SIZES).map(([key, [width, height]]) => ({
    key,
    width,
    height,
    source: transparent,
    prompt: 'An original contextual fixture',
  }));
  await publishContextArt(inputs, output);
  const manifest = JSON.parse(await readFile(join(output, 'manifest.json'), 'utf8'));
  assert.equal(manifest.version, 1);
  assert.equal(manifest.delivery.quality, 94);
  assert.equal(Object.keys(manifest.assets).length, 10);
  let total = 0;
  for (const [key, [width, height]] of Object.entries(CONTEXT_ART_SIZES)) {
    const bytes = await readFile(join(output, `${key}.webp`));
    const record = manifest.assets[key];
    assert.deepEqual([record.width, record.height, record.bytes], [width, height, bytes.length]);
    assert.ok(bytes.length <= 16 * 1024);
    total += bytes.length;
  }
  assert.equal(manifest.total_bytes, total);
  assert.ok(total + Buffer.byteLength(JSON.stringify(manifest)) <= 96 * 1024);
  await assert.rejects(publishContextArt(inputs, output), /already exists|immutable/i);
});

test('invalid dimensions, duplicate/missing keys and missing sources do not publish a context pack', async () => {
  const inputs = Object.entries(CONTEXT_ART_SIZES).map(([key, [width, height]]) => ({
    key,
    width,
    height,
    source: transparent,
    prompt: 'Fixture',
  }));
  await assert.rejects(
    publishContextArt(
      [{ ...inputs[0], width: 200 }, ...inputs.slice(1)],
      join(directory, 'bad-size')
    ),
    /dimension/i
  );
  await assert.rejects(
    publishContextArt([...inputs.slice(0, -1), inputs[0]], join(directory, 'bad-keys')),
    /keys|duplicate/i
  );
  const target = join(directory, 'bad-budget');
  await assert.rejects(
    publishContextArt(
      inputs.map(input => ({ ...input, source: '' })),
      target
    ),
    /source/i
  );
  await assert.rejects(readdir(target), { code: 'ENOENT' });
});

test('a complete staging pack that exceeds its manifest-inclusive budget remains unpublished', async () => {
  const output = join(directory, 'too-large');
  await assert.rejects(
    publishImmutablePack(output, 32, async stage => {
      await writeFile(join(stage, 'body.webp'), Buffer.alloc(32));
      return { total_bytes: 32, assets: {} };
    }),
    /budget/i
  );
  await assert.rejects(readdir(output), { code: 'ENOENT' });
});
