/** Measure delivered bytes, native manifests and encoded media after packaging.
 * No render, audio conversion, publication or approval is performed here.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat, readFile, realpath, rename, writeFile } from 'node:fs/promises';
import { registerHooks } from 'node:module';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { PRESENTATION_REVISION } from '../src/presentation-plan.ts';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.resolve(root, 'exports/lia-motion');
const COMMAND_TIMEOUT_MS = 60_000;
const LIMITS = {
  webIntegratedLufs: -16,
  masterIntegratedLufs: -23,
  integratedToleranceLufs: 0.5,
  maximumTruePeakDbtp: -1,
  aacTruePeakToleranceDb: 0.15,
  pcmTruePeakToleranceDb: 0.03,
  audioSampleRate: 48_000,
  audioChannels: 2,
  aacPaddingSamples: 1024,
};

const samePath = (left, right) =>
  process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;

export async function loadNativeSchemas() {
  // Load the exact schemas used by the application. Node strips their types;
  // the sole alias is the application's configured, CSP-compatible Zod seam.
  const zodUrl = pathToFileURL(path.resolve(root, 'apps/web/src/lib/zod.ts')).href;
  const mediaUrl = pathToFileURL(path.resolve(root, 'apps/web/src/lib/landing/media.ts')).href;
  const beatsUrl = pathToFileURL(
    path.resolve(root, 'apps/web/src/lib/landing/beats-schema.ts')
  ).href;
  const nativeModules = new Set([zodUrl, mediaUrl, beatsUrl]);
  const hook = registerHooks({
    resolve(specifier, context, nextResolve) {
      const resolved = nextResolve(specifier === '@/lib/zod' ? zodUrl : specifier, context);
      // Next.js does not mark its package as ESM. Declare these known TS
      // modules explicitly rather than trigger Node's module-type guessing.
      return nativeModules.has(resolved.url)
        ? { ...resolved, format: 'module-typescript' }
        : resolved;
    },
  });
  try {
    const [media, beats] = await Promise.all([import(mediaUrl), import(beatsUrl)]);
    return {
      landingMediaManifestSchema: media.landingMediaManifestSchema,
      beatMapSchema: beats.beatMapSchema,
    };
  } finally {
    hook.deregister();
  }
}

async function regularFile(file) {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`Expected a regular file: ${file}`);
  return info;
}

function underOutput(file) {
  const relative = path.relative(output, file);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Path escapes the delivery directory: ${file}`);
  }
  return file;
}

async function assetFile(name) {
  // Callers obtain these names from the native manifest parser. Bounds and a
  // physical-path check also cover untrusted delivery metadata and symlinks.
  const file = underOutput(path.resolve(output, name));
  if (!samePath(path.dirname(file), output)) throw new Error(`Expected a bare asset name: ${name}`);
  await regularFile(file);
  if (!samePath(await realpath(file), file))
    throw new Error(`Asset resolves outside its declared path: ${name}`);
  return file;
}

async function readJson(file) {
  await regularFile(file);
  return JSON.parse(await readFile(file, 'utf8'));
}

async function sha256(file) {
  await regularFile(file);
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}

function run(command, args) {
  const result = spawnSync(command, args, {
    encoding: 'utf8',
    timeout: COMMAND_TIMEOUT_MS,
    maxBuffer: 8 * 1024 * 1024,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    throw new Error(
      `${command} failed: ${result.error?.message ?? result.stderr?.trim() ?? result.status}`
    );
  }
  return result;
}

export function frameRate(value) {
  const parts = String(value).split('/').map(Number);
  const rate = parts.length === 2 ? parts[0] / parts[1] : parts[0];
  if (!Number.isFinite(rate) || rate <= 0) throw new Error(`Invalid frame rate: ${value}`);
  return rate;
}

function checkMediaDuration(probe, video, audio, composition, master) {
  const expectedSeconds = composition.durationInFrames / composition.fps;
  const toleranceSeconds =
    1 / composition.fps + (master ? 0 : LIMITS.aacPaddingSamples / LIMITS.audioSampleRate);
  const durations = {
    container: Number(probe.format?.duration),
    video: Number(video.duration ?? probe.format?.duration),
    audio: Number(audio.duration ?? probe.format?.duration),
  };
  for (const [kind, seconds] of Object.entries(durations)) {
    assert.ok(
      Number.isFinite(seconds) && Math.abs(seconds - expectedSeconds) <= toleranceSeconds,
      `${kind} duration ${seconds} differs from ${expectedSeconds}, tolerance ${toleranceSeconds}`
    );
  }
  return { expectedSeconds, toleranceSeconds, measuredSeconds: durations };
}

export function checkEncodedStreams(probe, composition, dimensions, master = false) {
  const videos = probe.streams?.filter(stream => stream.codec_type === 'video') ?? [];
  const audios = probe.streams?.filter(stream => stream.codec_type === 'audio') ?? [];
  assert.equal(videos.length, 1, 'exactly one video stream is required');
  assert.equal(audios.length, 1, 'exactly one audio stream is required');
  const video = videos[0];
  const audio = audios[0];
  assert.equal(video.width, dimensions[0], 'encoded width');
  assert.equal(video.height, dimensions[1], 'encoded height');
  const fps = frameRate(video.avg_frame_rate || video.r_frame_rate);
  assert.ok(Math.abs(fps - composition.fps) < 0.001, `frame rate ${fps} != ${composition.fps}`);
  assert.equal(Number(audio.sample_rate), LIMITS.audioSampleRate, 'audio sample rate');
  assert.equal(audio.channels, LIMITS.audioChannels, 'audio channel count');
  assert.equal(audio.channel_layout, 'stereo', 'audio channel layout');
  assert.equal(video.color_space, 'bt709', 'video colour space');
  assert.equal(video.color_primaries, 'bt709', 'video colour primaries');
  assert.equal(video.color_transfer, 'bt709', 'video transfer characteristic');
  if (master) {
    assert.equal(video.codec_name, 'prores', 'master video codec');
    assert.equal(video.profile, 'HQ', 'master ProRes profile');
    assert.equal(video.pix_fmt, 'yuv422p10le', 'master pixel format');
    assert.equal(fps, 25, 'master frame rate');
    assert.equal(audio.codec_name, 'pcm_s24le', 'master PCM codec');
    assert.equal(Number(audio.bits_per_sample), 24, 'master PCM sample depth');
  } else {
    assert.equal(video.codec_name, 'h264', 'web video codec');
    assert.equal(video.pix_fmt, 'yuv420p', 'web pixel format');
    assert.equal(audio.codec_name, 'aac', 'web audio codec');
  }
  return { ...checkMediaDuration(probe, video, audio, composition, master), fps, video, audio };
}

function probeMedia(file) {
  return JSON.parse(
    run('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file]).stdout
  );
}

function measureAudio(file) {
  const diagnostic = run('ffmpeg', [
    '-hide_banner',
    '-nostdin',
    '-i',
    file,
    '-map',
    '0:a:0',
    '-vn',
    '-sn',
    '-dn',
    '-af',
    'loudnorm=I=-23:LRA=7:TP=-1:print_format=json',
    '-f',
    'null',
    '-',
  ]).stderr;
  const end = diagnostic.lastIndexOf('}');
  const start = diagnostic.lastIndexOf('{', end);
  if (start < 0 || end < start) throw new Error('FFmpeg did not return its loudness measurement');
  return JSON.parse(diagnostic.slice(start, end + 1));
}

export function checkLoudness(measurement, master = false) {
  // input_* describes the actual delivered audio, before this measurement
  // filter's hypothetical normalized output. Packaging's input report is not
  // accepted as a measurement of the encoded delivery.
  const integratedLufs = Number(measurement.input_i);
  const truePeakDbtp = Number(measurement.input_tp);
  assert.ok(
    Number.isFinite(integratedLufs) && Number.isFinite(truePeakDbtp),
    'finite audio measurements'
  );
  assert.ok(
    Math.abs(integratedLufs - (master ? LIMITS.masterIntegratedLufs : LIMITS.webIntegratedLufs)) <= LIMITS.integratedToleranceLufs,
    `integrated loudness ${integratedLufs} LUFS is outside the measured acceptance window`
  );
  const toleranceDb = master ? LIMITS.pcmTruePeakToleranceDb : LIMITS.aacTruePeakToleranceDb;
  assert.ok(
    truePeakDbtp <= LIMITS.maximumTruePeakDbtp + toleranceDb,
    `true peak ${truePeakDbtp} dBTP exceeds ${LIMITS.maximumTruePeakDbtp + toleranceDb}`
  );
  return { integratedLufs, truePeakDbtp, toleranceDb, ffmpegMeasurement: measurement };
}

const descriptorOf = parsed => {
  const { version: _version, next: _next, presentation: _presentation, ...descriptor } = parsed;
  return descriptor;
};

async function verifyRecord(record, composition, schemas) {
  const descriptor = descriptorOf(
    schemas.landingMediaManifestSchema.parse({
      version: 1,
      ...record.descriptor,
      next: [],
    })
  );
  assert.equal(
    descriptor.durationSeconds,
    composition.durationInFrames / composition.fps,
    'manifest duration matches the composition inventory'
  );
  assert.deepEqual(descriptor.aspectRatio, [16, 9], 'declared aspect ratio');
  assert.equal(descriptor.renditions.length, 2, 'HD and mobile renditions are required');
  assert.ok(descriptor.beats, 'a packaged beat map is required');
  const names = [
    descriptor.poster,
    ...descriptor.renditions.map(item => item.src),
    descriptor.beats,
  ];
  assert.deepEqual(
    Object.keys(record.assets ?? {}).sort(),
    [...names].sort(),
    'complete asset hashes'
  );
  const assets = [];
  for (const name of names) {
    const file = await assetFile(name);
    const expectedHash = record.assets[name];
    assert.match(expectedHash, /^[a-f0-9]{64}$/, 'recorded SHA-256');
    const actualHash = await sha256(file);
    assert.equal(actualHash, expectedHash, `delivered byte checksum: ${name}`);
    assert.ok(
      name.endsWith(`-${actualHash.slice(0, 12)}${path.extname(name)}`),
      `immutable asset name: ${name}`
    );
    assets.push({ file: name, bytes: (await lstat(file)).size, sha256: actualHash });
  }
  assert.equal(record.sha256, record.assets[descriptor.renditions[0].src], 'HD checksum summary');
  const beats = schemas.beatMapSchema.parse(await readJson(await assetFile(descriptor.beats)));
  assert.ok(beats.beats.length > 0, 'at least one beat is required');
  assert.ok(
    beats.beats.every(([ms]) => ms < descriptor.durationSeconds * 1000),
    'beats stay within this edit'
  );
  const videos = [];
  for (const [index, rendition] of descriptor.renditions.entries()) {
    const file = await assetFile(rendition.src);
    const encoded = checkEncodedStreams(
      probeMedia(file),
      composition,
      index === 0 ? [1920, 1080] : [1280, 720]
    );
    const audio = checkLoudness(measureAudio(file));
    videos.push({ file: rendition.src, ...encoded, measuredAudio: audio });
  }
  return { name: record.name, assets, beatCount: beats.beats.length, videos };
}

async function verifyPackagedMode(mode, compositions, expectedNames, schemas, music) {
  const delivery = await readJson(underOutput(path.resolve(output, `${mode}-delivery.json`)));
  assert.equal(delivery.generation, PRESENTATION_REVISION, 'delivery belongs to the active revision');
  assert.deepEqual(
    delivery.music,
    {
      title: music.title,
      artist: music.artist,
      license: music.license,
      sourceSha256: music.sourceSha256,
      provider: music.provider ?? null,
      model: music.model ?? null,
      generationMetadata: music.generationMetadata ?? null,
      beatAnalysisVersion: music.analysisVersion,
    },
    'soundtrack provenance matches current authoring metadata'
  );
  assert.deepEqual(
    delivery.records?.map(record => record.name).sort(),
    [...expectedNames].sort(),
    `complete ${mode} delivery`
  );
  const manifestEntries = new Map();
  if (mode === 'main') {
    const parsed = schemas.landingMediaManifestSchema.parse(
      await readJson(path.resolve(output, 'manifest.json'))
    );
    assert.equal(parsed.next.length, 1, 'main manifest carries the full edit after landing');
    assert.deepEqual(parsed.presentation, parsed.next[0], 'exclusive presentation names the complete film');
    manifestEntries.set('landing', descriptorOf(parsed));
    manifestEntries.set('full', parsed.next[0]);
  } else {
    const directory = path.resolve(output, 'focus-manifests');
    const info = await lstat(directory);
    assert.ok(info.isDirectory() && !info.isSymbolicLink(), 'physical focus manifest directory');
    assert.ok(
      samePath(await realpath(directory), directory),
      'focus directory stays in the export root'
    );
    for (const name of expectedNames) {
      const parsed = schemas.landingMediaManifestSchema.parse(
        await readJson(underOutput(path.resolve(directory, `${name}.json`)))
      );
      assert.equal(parsed.next.length, 0, 'a standalone focus has no undeclared following video');
      manifestEntries.set(name, descriptorOf(parsed));
    }
  }
  const records = [];
  for (const record of delivery.records) {
    const expectedDescriptor = descriptorOf(
      schemas.landingMediaManifestSchema.parse({
        version: 1,
        ...record.descriptor,
        next: [],
      })
    );
    assert.deepEqual(
      manifestEntries.get(record.name),
      expectedDescriptor,
      `published descriptor: ${record.name}`
    );
    const composition = compositions.find(
      item => item.id.replace(/^LIA-/, '').toLowerCase() === record.name
    );
    assert.ok(composition, `missing composition: ${record.name}`);
    records.push(await verifyRecord(record, composition, schemas));
    console.log(
      `Qualified ${record.name}: delivered checksums, native schemas, two encoded renditions and measured audio.`
    );
  }
  return {
    records,
    edits: records.length,
    encodedVideos: records.reduce((count, record) => count + record.videos.length, 0),
  };
}

async function verifyMaster(compositions) {
  const composition = compositions.find(item => item.id === 'LIA-Master25');
  assert.ok(composition, '25 fps master composition is present');
  const file = await assetFile('master25.mov');
  const encoded = checkEncodedStreams(probeMedia(file), composition, [1920, 1080], true);
  const measuredAudio = checkLoudness(measureAudio(file), true);
  console.log(
    'Qualified master25: ProRes HQ, 10-bit 4:2:2, 25 fps, stereo PCM 24-bit/48 kHz and measured audio.'
  );
  return {
    file: 'master25.mov',
    bytes: (await lstat(file)).size,
    sha256: await sha256(file),
    ...encoded,
    measuredAudio,
  };
}

async function prepareQualification(mode) {
  if (!['main', 'focus', 'master', 'all'].includes(mode))
    throw new Error('Verification mode must be main, focus, master or all');
  const info = await lstat(output);
  assert.ok(info.isDirectory() && !info.isSymbolicLink(), 'physical delivery root');
  assert.ok(
    samePath(await realpath(output), output),
    'delivery root resolves within the intended workspace'
  );
  const schemas = await loadNativeSchemas();
  const { PRESENTATION_FOCUS_PLAN: FOCUS_SCENES } = await import(
    pathToFileURL(path.resolve(project, 'src/presentation-plan.ts')).href
  );
  const compositions = await readJson(path.resolve(output, 'compositions.json'));
  assert.ok(Array.isArray(compositions), 'composition inventory is an array');
  for (const composition of compositions) {
    assert.ok(
      typeof composition.id === 'string' &&
        Number.isFinite(composition.fps) &&
        composition.fps > 0 &&
        Number.isInteger(composition.durationInFrames) &&
        composition.durationInFrames > 0,
      'valid composition timing'
    );
  }
  assert.equal(
    new Set(compositions.map(item => item.id)).size,
    compositions.length,
    'unique composition ids'
  );
  const music = await readJson(path.resolve(project, 'src/music-film.json'));
  const report = {
    version: 1,
    generation: PRESENTATION_REVISION,
    mode,
    checkedAt: new Date().toISOString(),
    scope:
      'Local technical measurements of delivered files; no human editorial review or broadcaster acceptance is asserted.',
    nativeSchemas: [
      'apps/web/src/lib/landing/media.ts',
      'apps/web/src/lib/landing/beats-schema.ts',
    ],
    nativeSchemaSha256: {
      media: await sha256(path.resolve(root, 'apps/web/src/lib/landing/media.ts')),
      beats: await sha256(path.resolve(root, 'apps/web/src/lib/landing/beats-schema.ts')),
    },
    tools: {
      node: process.version,
      ffprobe: run('ffprobe', ['-version']).stdout.split('\n')[0].trim(),
      ffmpeg: run('ffmpeg', ['-version']).stdout.split('\n')[0].trim(),
    },
    acceptance: { ...LIMITS, commandTimeoutMs: COMMAND_TIMEOUT_MS },
    compositionInventorySha256: await sha256(path.resolve(output, 'compositions.json')),
    results: {},
    failures: [],
    passed: false,
  };
  return { FOCUS_SCENES, compositions, schemas, music, report };
}

async function writeQualificationReport(report) {
  const mode = report.mode;
  const name = `${mode}-qualification.json`;
  const destination = underOutput(path.resolve(output, name));
  try {
    const previous = await lstat(destination);
    assert.ok(previous.isFile() && !previous.isSymbolicLink(), 'report target is a regular file');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const working = underOutput(
    path.resolve(output, `${mode}-qualification-${process.pid}-working.json`)
  );
  await writeFile(working, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  await rename(working, destination);
  console.log(`${report.passed ? 'PASS' : 'FAIL'}: ${destination}`);
}

export async function qualifyDelivery(mode = 'all') {
  const { FOCUS_SCENES, compositions, schemas, music, report } = await prepareQualification(mode);
  for (const selected of mode === 'all' ? ['main', 'focus', 'master'] : [mode]) {
    try {
      report.results[selected] =
        selected === 'master'
          ? await verifyMaster(compositions)
          : await verifyPackagedMode(
              selected,
              compositions,
              selected === 'main' ? ['landing', 'full'] : FOCUS_SCENES.map(scene => scene.id),
              schemas,
              music
            );
    } catch (error) {
      report.failures.push({ mode: selected, error: error.message });
      console.error(`Qualification failed for ${selected}: ${error.message}`);
    }
  }
  report.passed = report.failures.length === 0;
  await writeQualificationReport(report);
  return report;
}

if (process.argv[1] && samePath(path.resolve(process.argv[1]), fileURLToPath(import.meta.url))) {
  try {
    const report = await qualifyDelivery(process.argv[2] ?? 'all');
    process.exitCode = report.passed ? 0 : 1;
  } catch (error) {
    console.error(`Delivery qualification could not run: ${error.message}`);
    process.exitCode = 1;
  }
}
