import { createReadStream } from 'node:fs';
import { mkdir, readFile, writeFile, lstat, realpath, rename, unlink } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { measuredLoudnessFilter, runFfmpeg } from './audio-master.mjs';
import { PRESENTATION_REVISION } from '../src/presentation-plan.ts';
import { loadNativeSchemas } from './verify-delivery.mjs';
import {
  buildMainManifest,
  loadPreservedPlaylist,
  verifyPreservedAssets,
} from './preserved-playlist.ts';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.resolve(root, 'exports/lia-motion');
const BARE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const HASH_LENGTH = 12;
const samePath = (left, right) =>
  process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;

/** Exact exported names only: `main`, or `focus focus-avatars focus-voice`.
 * A partial selection preserves already packaged records of the same mode.
 */
export function selectCompositions(compositions, mode, requestedNames = []) {
  if (!['main', 'focus'].includes(mode)) {
    throw new Error('Package mode must be main or focus');
  }
  if (!Array.isArray(compositions)) throw new Error('Invalid compositions inventory');
  const available = compositions.filter(item =>
    mode === 'focus'
      ? typeof item.id === 'string' && /^LIA-focus-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.id)
      : ['LIA-Landing', 'LIA-Full'].includes(item.id)
  );
  const names = available.map(item => item.id.replace(/^LIA-/, '').toLowerCase());
  if (new Set(names).size !== names.length) throw new Error('Duplicate composition names');
  if (new Set(requestedNames).size !== requestedNames.length)
    throw new Error('Duplicate requested names');
  for (const name of requestedNames) {
    if (!names.includes(name)) {
      throw new Error(
        `No ${mode} composition named ${JSON.stringify(name)}; use an exact exported name`
      );
    }
  }
  const selected = available.filter(
    (_, index) => !requestedNames.length || requestedNames.includes(names[index])
  );
  if (!selected.length) throw new Error(`No ${mode} compositions to package`);
  for (const item of available) {
    if (
      !Number.isFinite(item.fps) ||
      item.fps <= 0 ||
      !Number.isInteger(item.durationInFrames) ||
      item.durationInFrames <= 0
    ) {
      throw new Error(`Invalid composition timing: ${item.id}`);
    }
  }
  return { available, selected };
}

/** Each published asset identifies its own bytes, rather than its source MP4. */
export function hashedFileName(stem, extension, sha256) {
  if (!BARE_NAME.test(stem) || !/^\.[a-z0-9]+$/.test(extension) || !/^[a-f0-9]{64}$/.test(sha256)) {
    throw new Error('Invalid content-addressed asset name');
  }
  return `${stem}-${sha256.slice(0, HASH_LENGTH)}${extension}`;
}

function exportPath(directory, name) {
  if (!BARE_NAME.test(name)) throw new Error(`A media file must have a bare name: ${name}`);
  const result = path.resolve(directory, name);
  if (!samePath(path.dirname(result), directory))
    throw new Error(`Media path escapes its export directory: ${name}`);
  const relativeDirectory = path.relative(output, directory);
  if (relativeDirectory.startsWith('..') || path.isAbsolute(relativeDirectory)) {
    throw new Error('Export directory escapes the media root');
  }
  return result;
}

async function existingFile(file) {
  let info;
  try {
    info = await lstat(file);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
  if (info.isSymbolicLink() || !info.isFile())
    throw new Error(`Expected a regular export file: ${file}`);
  return info;
}

async function sha256File(file) {
  if (!(await existingFile(file))) throw new Error(`Missing export file: ${file}`);
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}

async function workingFile(name) {
  const file = exportPath(output, name);
  await existingFile(file); // Reject a symlink before FFmpeg's -y can follow it.
  return file;
}

async function publishFile(working, stem, extension) {
  if (!samePath(path.dirname(working), output))
    throw new Error('Working file escapes the media root');
  const sha256 = await sha256File(working);
  const name = hashedFileName(stem, extension, sha256);
  const published = exportPath(output, name);
  if (await existingFile(published)) {
    if ((await sha256File(published)) !== sha256)
      throw new Error(`Content hash collision: ${name}`);
    await unlink(working);
  } else {
    // Both paths were verified inside the physical export root; no shell move.
    await rename(working, published);
  }
  return { name, sha256 };
}

async function writeMetadata(directory, name, value) {
  const destination = exportPath(directory, name);
  const working = exportPath(directory, `${path.basename(name, '.json')}-working.json`);
  await existingFile(destination);
  await existingFile(working);
  await writeFile(working, JSON.stringify(value, null, 2) + '\n');
  await rename(working, destination);
}

/** A preserved descriptor is usable only with its complete immutable assets. */
async function verifyPreviousRecord(record, mode) {
  const descriptor = record.descriptor;
  if (
    !descriptor ||
    !Array.isArray(descriptor.renditions) ||
    descriptor.renditions.length !== 2 ||
    typeof descriptor.beats !== 'string'
  ) {
    throw new Error(`Invalid previous descriptor: ${record.name}`);
  }
  const names = [
    descriptor.poster,
    ...descriptor.renditions.map(item => item.src),
    descriptor.beats,
  ];
  for (const name of names) {
    if (
      typeof name !== 'string' ||
      !BARE_NAME.test(name) ||
      !/-[a-f0-9]{12}\.(mp4|webp|json)$/.test(name)
    ) {
      throw new Error(
        `Previous ${record.name} assets are not content-addressed; package the whole ${mode} mode first`
      );
    }
    const hash = await sha256File(exportPath(output, name));
    const shortHash = name.match(/-([a-f0-9]{12})\.[a-z0-9]+$/)[1];
    if (!hash.startsWith(shortHash)) throw new Error(`Previous asset hash mismatch: ${name}`);
  }
}

async function preserveRecords(mode, available, selected, partial, music) {
  if (!partial) return [];
  const delivery = exportPath(output, `${mode}-delivery.json`);
  if (!(await existingFile(delivery))) return [];
  const previous = JSON.parse(await readFile(delivery, 'utf8'));
  if (previous.generation !== PRESENTATION_REVISION) return [];
  if (!Array.isArray(previous.records)) throw new Error('Invalid previous delivery records');
  const availableNames = new Set(available.map(item => item.id.replace(/^LIA-/, '').toLowerCase()));
  const selectedNames = new Set(selected.map(item => item.id.replace(/^LIA-/, '').toLowerCase()));
  const kept = previous.records.filter(
    record => availableNames.has(record.name) && !selectedNames.has(record.name)
  );
  if (kept.length && previous.music?.sourceSha256 !== music.sourceSha256) {
    throw new Error(
      `Music source changed; package the whole ${mode} mode before preserving records`
    );
  }
  if (new Set(kept.map(record => record.name)).size !== kept.length)
    throw new Error('Duplicate previous delivery records');
  for (const record of kept) await verifyPreviousRecord(record, mode);
  return kept;
}

async function focusDirectory() {
  const directory = exportPath(output, 'focus-manifests');
  try {
    const info = await lstat(directory);
    if (info.isSymbolicLink() || !info.isDirectory())
      throw new Error('Expected a regular focus manifest directory');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    await mkdir(directory);
  }
  if (!samePath(await realpath(directory), directory))
    throw new Error('Focus manifest directory points outside its export path');
  return directory;
}

async function packageMedia() {
  const mode = process.argv[2] ?? 'main';
  const requestedNames = process.argv.slice(3);
  if (!['main', 'focus', 'playlist'].includes(mode))
    throw new Error('Package mode must be main, focus or playlist');
  // Resolve the physical target once before any file is written or renamed.
  if (!samePath(await realpath(output), output))
    throw new Error('Media export root must be a physical workspace directory');
  const schemas = mode === 'focus' ? null : await loadNativeSchemas();
  const preserved = schemas ? await loadPreservedPlaylist(schemas) : null;
  if (preserved) await verifyPreservedAssets(preserved, output, schemas);
  if (mode === 'playlist') {
    if (requestedNames.length)
      throw new Error('Playlist-only packaging accepts no composition names');
    const delivery = JSON.parse(await readFile(exportPath(output, 'main-delivery.json'), 'utf8'));
    if (delivery.generation !== PRESENTATION_REVISION || !Array.isArray(delivery.records))
      throw new Error('A current main delivery is required before playlist-only packaging');
    const landing = delivery.records.find(record => record.name === 'landing');
    const full = delivery.records.find(record => record.name === 'full');
    if (!landing || !full || delivery.records.length !== 2)
      throw new Error('Playlist-only packaging requires the existing landing and full records');
    for (const record of delivery.records) await verifyPreviousRecord(record, 'main');
    const manifest = buildMainManifest(landing.descriptor, full.descriptor, preserved, schemas);
    await writeMetadata(output, 'manifest.json', manifest);
    console.log(
      `Updated public playlist: ${1 + manifest.next.length} videos; no render or audio conversion.`
    );
    return;
  }
  const music = JSON.parse(await readFile(path.resolve(project, 'src/music-film.json'), 'utf8'));
  const compositions = JSON.parse(await readFile(exportPath(output, 'compositions.json'), 'utf8'));
  const { available, selected } = selectCompositions(compositions, mode, requestedNames);
  const records = await preserveRecords(
    mode,
    available,
    selected,
    requestedNames.length > 0,
    music
  );
  const selectedNames = selected.map(item => item.id.replace(/^LIA-/, '').toLowerCase());
  const allNames = new Set([...records.map(record => record.name), ...selectedNames]);
  if (mode === 'main' && (!allNames.has('landing') || !allNames.has('full'))) {
    throw new Error(
      'Both main edits must be packaged; use main without a name for the first delivery'
    );
  }
  for (const name of selectedNames) {
    if (!(await existingFile(exportPath(output, `${name}.mp4`))))
      throw new Error(`Render ${name}.mp4 before packaging`);
  }

  const updatedRecords = [];
  for (const composition of selected) {
    const name = composition.id.replace(/^LIA-/, '').toLowerCase();
    const source = exportPath(output, `${name}.mp4`);
    // The landing has its own playback level; the separate TV master remains -23 LUFS.
    const normalized = measuredLoudnessFilter(['-i', source], '', -16);
    const hdWorking = await workingFile(`${name}-1080-working.mp4`);
    runFfmpeg([
      '-i',
      source,
      '-c:v',
      'copy',
      '-af',
      normalized.filter,
      '-c:a',
      'aac',
      '-b:a',
      '320k',
      '-ar',
      '48000',
      '-movflags',
      '+faststart',
      hdWorking,
    ]);
    const hd = await publishFile(hdWorking, `${name}-1080`, '.mp4');
    const mobileWorking = await workingFile(`${name}-720-working.mp4`);
    runFfmpeg([
      '-i',
      exportPath(output, hd.name),
      '-vf',
      'scale=1280:720',
      '-c:v',
      'libx264',
      '-crf',
      '18',
      '-preset',
      'medium',
      '-c:a',
      'copy',
      '-movflags',
      '+faststart',
      mobileWorking,
    ]);
    const mobile = await publishFile(mobileWorking, `${name}-720`, '.mp4');
    const posterWorking = await workingFile(`${name}-poster-working.webp`);
    runFfmpeg([
      '-ss',
      String(mode === 'main' ? (name === 'full' ? 11 : 7) : 4),
      '-i',
      source,
      '-frames:v',
      '1',
      '-c:v',
      'libwebp',
      '-quality',
      '92',
      posterWorking,
    ]);
    const poster = await publishFile(posterWorking, `${name}-poster`, '.webp');
    const duration = composition.durationInFrames / composition.fps;
    const beatBytes =
      JSON.stringify({
        version: 1,
        beats: music.beatEntries.filter(([ms]) => ms < duration * 1000),
      }) + '\n';
    const beatsWorking = await workingFile(`${name}-beats-working.json`);
    await writeFile(beatsWorking, beatBytes);
    const beats = await publishFile(beatsWorking, `${name}-beats`, '.json');
    const descriptor = {
      poster: poster.name,
      renditions: [
        { src: hd.name, type: 'video/mp4', minWidth: 900 },
        { src: mobile.name, type: 'video/mp4' },
      ],
      aspectRatio: [16, 9],
      durationSeconds: duration,
      beats: beats.name,
      credit: null,
      aiGenerated: music.id === 'lia-original-score',
    };
    const verify = spawnSync(
      'ffprobe',
      [
        '-v',
        'error',
        '-show_entries',
        'format=duration:stream=codec_name,width,height,sample_rate',
        '-of',
        'json',
        exportPath(output, hd.name),
      ],
      { encoding: 'utf8' }
    );
    if (verify.status !== 0) throw new Error(verify.stderr || `ffprobe failed for ${name}`);
    const record = {
      name,
      descriptor,
      audioMeasurement: normalized.measurement,
      sha256: hd.sha256,
      assets: Object.fromEntries(
        [hd, mobile, poster, beats].map(asset => [asset.name, asset.sha256])
      ),
      probe: JSON.parse(verify.stdout),
    };
    records.push(record);
    updatedRecords.push(record);
    console.log(
      `Packaged ${name}: content-addressed HD/mobile, poster, beat map and measured audio.`
    );
  }
  const ordered = available
    .map(item => records.find(record => record.name === item.id.replace(/^LIA-/, '').toLowerCase()))
    .filter(Boolean);
  if (mode === 'main') {
    const landing = ordered.find(record => record.name === 'landing');
    const full = ordered.find(record => record.name === 'full');
    await writeMetadata(
      output,
      'manifest.json',
      buildMainManifest(landing.descriptor, full.descriptor, preserved, schemas)
    );
  } else {
    const directory = await focusDirectory();
    for (const record of updatedRecords) {
      await writeMetadata(directory, `${record.name}.json`, {
        version: 1,
        ...record.descriptor,
        next: [],
      });
    }
  }
  await writeMetadata(output, `${mode}-delivery.json`, {
    generation: PRESENTATION_REVISION,
    music: {
      title: music.title,
      artist: music.artist,
      license: music.license,
      sourceSha256: music.sourceSha256,
      provider: music.provider ?? null,
      model: music.model ?? null,
      generationMetadata: music.generationMetadata ?? null,
      beatAnalysisVersion: music.analysisVersion,
    },
    records: ordered,
  });
  console.log(
    `Updated ${mode} delivery: ${updatedRecords.length} packaged, ${ordered.length - updatedRecords.length} preserved.`
  );
}

if (process.argv[1] && samePath(path.resolve(process.argv[1]), fileURLToPath(import.meta.url))) {
  await packageMedia();
}
