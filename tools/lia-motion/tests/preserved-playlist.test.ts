import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, rmdir, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import test from 'node:test';
import * as helpers from '../scripts/preserved-playlist.ts';

const { loadNativeSchemas, checkPreservedStreams } = await import(
  new URL('../scripts/verify-delivery.mjs', import.meta.url).href
);
const schemas = await loadNativeSchemas();
const raw = JSON.parse(
  await readFile(new URL('../scripts/preserved-playlist.json', import.meta.url), 'utf8')
);
const config = helpers.validatePreservedPlaylist(raw, schemas);
const landing = {
  poster: 'landing.webp',
  renditions: [{ src: 'landing.mp4', type: 'video/mp4' }],
  durationSeconds: 65,
};
const full = {
  poster: 'full.webp',
  renditions: [{ src: 'full.mp4', type: 'video/mp4' }],
  durationSeconds: 158,
};

test('packaging preserves both historical films after teaser/full and keeps the dedicated presentation', () => {
  const manifest = helpers.buildMainManifest(landing, full, config, schemas);
  assert.deepEqual(
    [manifest.poster, ...manifest.next.map((entry: { poster: string }) => entry.poster)],
    [
      'landing.webp',
      'full.webp',
      'underclass-7dfdd6a89a1b-poster.webp',
      'stopshipping-64dc639bc976-poster.webp',
    ]
  );
  assert.deepEqual(manifest.presentation, manifest.next[0]);
  assert.equal(manifest.next[1].durationSeconds, 306.48);
  assert.equal(manifest.next[2].durationSeconds, 251.477);
  assert.equal(manifest.next[1].renditions.length, 4);
  assert.equal(manifest.next[2].renditions.length, 2);
  assert.deepEqual(manifest.next[1].credit, {
    label: '@anabology',
    url: 'https://x.com/anabology',
  });
  assert.deepEqual(manifest.next[2].credit, {
    label: '@vikktorrrre',
    url: 'https://x.com/vikktorrrre',
  });
  assert.ok(manifest.next[1].aiGenerated && manifest.next[2].aiGenerated);
  assert.equal(raw.assets.length, 10);
});

test('delivery rejects missing, reordered or changed historical entries and an incorrect presentation', () => {
  const manifest = helpers.buildMainManifest(landing, full, config, schemas);
  const mutated = [
    { ...manifest, next: manifest.next.slice(0, 1) },
    { ...manifest, next: [manifest.next[0], manifest.next[2], manifest.next[1]] },
    {
      ...manifest,
      next: [manifest.next[0], { ...manifest.next[1], credit: null }, manifest.next[2]],
    },
    { ...manifest, presentation: manifest.next[1] },
  ];
  helpers.validateMainPlaylist(manifest, landing, full, config, schemas);
  for (const changed of mutated)
    assert.throws(() => helpers.validateMainPlaylist(changed, landing, full, config, schemas));
});

test('preserved configuration refuses unsafe paths and incomplete or duplicated fingerprints', () => {
  for (const changed of [
    { ...raw, assets: raw.assets.slice(1) },
    { ...raw, assets: [...raw.assets, raw.assets[0]] },
    { ...raw, assets: [{ ...raw.assets[0], name: '../outside' }, ...raw.assets.slice(1)] },
    { ...raw, assets: [{ ...raw.assets[0], sha256: 'unknown' }, ...raw.assets.slice(1)] },
    { ...raw, videos: [raw.videos[0], raw.videos[0]] },
  ])
    assert.throws(() => helpers.validatePreservedPlaylist(changed, schemas));
});

test('all legacy renditions resolve under the same versioned GitHub media base', async () => {
  const native = await import(
    new URL('../../../apps/web/src/lib/landing/media.ts', import.meta.url).href
  );
  const manifest = helpers.buildMainManifest(landing, full, config, schemas);
  const base = 'https://github.com/owner/project/releases/download/v3.0.0';
  const resolved = native.resolveLandingPlaylist(manifest, base);
  assert.equal(resolved.length, 4);
  for (const video of resolved) {
    assert.ok(video.poster.startsWith(base + '/'));
    for (const rendition of video.renditions) assert.ok(rendition.src.startsWith(base + '/'));
  }
});

test('legacy verification accepts original AV1/24fps without imposing V6 codec or soundtrack constraints', () => {
  const descriptor = { aspectRatio: [16, 9], durationSeconds: 7 };
  const rendition = { type: 'video/mp4; codecs="av01.0.05M.10"' };
  const probe = {
    format: { duration: '7.023' },
    streams: [
      {
        codec_type: 'video',
        codec_name: 'av1',
        width: 1280,
        height: 720,
        avg_frame_rate: '24/1',
        pix_fmt: 'yuv420p10le',
      },
      { codec_type: 'audio', codec_name: 'aac', sample_rate: '44100' },
    ],
  };
  assert.equal(checkPreservedStreams(probe, descriptor, rendition).fps, 24);
  for (const changed of [
    { ...probe, format: { duration: '22' } },
    { ...probe, streams: [{ ...probe.streams[0], codec_name: 'h264' }, probe.streams[1]] },
    { ...probe, streams: [{ ...probe.streams[0], height: 1000 }, probe.streams[1]] },
    { ...probe, streams: [probe.streams[0]] },
  ])
    assert.throws(() => checkPreservedStreams(changed, descriptor, rendition));
});

test('preserved bytes and beat maps are verified without rewriting files or imposing the new soundtrack', async () => {
  const directory = await realpath(await mkdtemp(path.join(tmpdir(), 'lia-preserved-fixture-')));
  const descriptor = {
    poster: 'poster.webp',
    renditions: [{ src: 'video.mp4', type: 'video/mp4' }],
    beats: 'beats.json',
    durationSeconds: 2,
  };
  const bodies = {
    'poster.webp': Buffer.from('original poster'),
    'video.mp4': Buffer.from('original video'),
    'beats.json': Buffer.from('{"version":1,"beats":[[100,0.5,true],[1500,1,false]]}\n'),
  };
  const assets = Object.entries(bodies).map(([name, body]) => ({
    name,
    bytes: body.length,
    sha256: createHash('sha256').update(body).digest('hex'),
  }));
  const fixture = helpers.validatePreservedPlaylist(
    { version: 1, videos: [{ id: 'historical', descriptor }], assets },
    schemas
  );
  try {
    for (const [name, body] of Object.entries(bodies))
      await writeFile(path.join(directory, name), body);
    const result = await helpers.verifyPreservedAssets(fixture, directory, schemas);
    assert.equal(result.records.length, 1);
    assert.equal(result.records[0].beatCount, 2);
    assert.equal(result.records[0].assets.length, 3);
    for (const [name, body] of Object.entries(bodies))
      assert.deepEqual(await readFile(path.join(directory, name)), body);
    await writeFile(path.join(directory, 'poster.webp'), 'changed bytes');
    await assert.rejects(helpers.verifyPreservedAssets(fixture, directory, schemas));
    await writeFile(path.join(directory, 'poster.webp'), bodies['poster.webp']);
    const outsideBeats = Buffer.from('{"version":1,"beats":[[2000,1,true]]}\n');
    await writeFile(path.join(directory, 'beats.json'), outsideBeats);
    const wrongTiming = helpers.validatePreservedPlaylist(
      {
        version: 1,
        videos: [{ id: 'historical', descriptor }],
        assets: assets.map(asset =>
          asset.name === 'beats.json'
            ? {
                ...asset,
                bytes: outsideBeats.length,
                sha256: createHash('sha256').update(outsideBeats).digest('hex'),
              }
            : asset
        ),
      },
      schemas
    );
    await assert.rejects(
      helpers.verifyPreservedAssets(wrongTiming, directory, schemas),
      /preserved beats stay/
    );
    await writeFile(path.join(directory, 'beats.json'), bodies['beats.json']);
    await unlink(path.join(directory, 'video.mp4'));
    await assert.rejects(helpers.verifyPreservedAssets(fixture, directory, schemas));
  } finally {
    for (const name of Object.keys(bodies))
      await unlink(path.join(directory, name)).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== 'ENOENT') throw error;
      });
    await rmdir(directory);
  }
});
