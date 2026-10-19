import { readFile, writeFile, mkdir, copyFile, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { landingBeats } from '../src/film/landing-beats.ts';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const previewOrigin = new URL(process.env.MOTION_PREVIEW_ORIGIN ?? 'http://localhost:3000');
if (!['http:', 'https:'].includes(previewOrigin.protocol) || previewOrigin.username || previewOrigin.password) {
  throw new Error('MOTION_PREVIEW_ORIGIN must be an HTTP(S) origin without credentials');
}
const previewBase = `${previewOrigin.origin}/landing-media-dev`;
const delivery = path.join(root, 'exports/lia-motion/feature-film-80s');
const destination = path.join(root, 'apps/web/public/landing-media-dev');
const source = path.join(delivery, 'lia-feature-film-1080p60.mp4');
const baseline = JSON.parse((await readFile(path.join(delivery, 'origin-manifest.json'), 'utf8')).replace(/^\uFEFF/, ''));
const score = JSON.parse(await readFile(path.join(project, 'public/audio/feature-film/score.json'), 'utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const records = [];
await access(source);
await mkdir(destination, { recursive: true });
function ffmpeg(args) {
  const process = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...args], { encoding: 'utf8', windowsHide: true });
  if (process.status !== 0) throw new Error(process.stderr);
}
async function publish(file, stem, extension) {
  const bytes = await readFile(file);
  const sha256 = digest(bytes);
  const name = `${stem}-${sha256.slice(0, 12)}.${extension}`;
  await writeFile(path.join(destination, name), bytes);
  records.push({ file: name, bytes: bytes.length, sha256 });
  return name;
}
// Distribution renditions have a bounded bitrate and short closed GOPs.
// Keep the high-quality authoring master; do not serve it directly on the web.
const full = path.join(delivery, 'lia-feature-film-web-1080p60.mp4');
const small = path.join(delivery, 'lia-feature-film-720p60.mp4');
function encodeWeb(output, height, maxrate, level) {
  ffmpeg(['-i', source, '-map', '0:v:0', '-map', '0:a:0',
    ...(height === 720 ? ['-vf', 'scale=1280:720:flags=lanczos'] : []),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-threads', '4',
    '-profile:v', 'high', '-level:v', level, '-refs', '3', '-pix_fmt', 'yuv420p',
    '-maxrate', `${maxrate}k`, '-bufsize', `${maxrate * 2}k`,
    '-g', '120', '-keyint_min', '120', '-sc_threshold', '0', '-flags', '+cgop',
    '-x264-params', 'open-gop=0', '-fps_mode', 'passthrough',
    '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', output]);
}
encodeWeb(full, 1080, 2000, '4.2');
encodeWeb(small, 720, 1000, '3.2');
const posterPath = path.join(delivery, 'poster.webp');
ffmpeg(['-ss', '1.8', '-i', source, '-frames:v', '1', '-c:v', 'libwebp', '-quality', '92', posterPath]);
const beatPath = path.join(delivery, 'beats.json');
await writeFile(beatPath, JSON.stringify({ version: 1, beats: landingBeats(score.transients.onsetTimesSeconds) }) + '\n');
const first = {
  poster: await publish(posterPath, 'lia-feature-poster', 'webp'),
  renditions: [
    { src: await publish(full, 'lia-feature-1080p60', 'mp4'), type: 'video/mp4', minWidth: 900 },
    { src: await publish(small, 'lia-feature-720p60', 'mp4'), type: 'video/mp4' },
  ],
  aspectRatio: [16, 9], durationSeconds: 80,
  beats: await publish(beatPath, 'lia-feature-beats', 'json'), credit: null, aiGenerated: true,
};
// The live origin currently contains the two independent illustration films.
// Preserve those exact entries and bytes after the replacement presentation.
const { version: _version, next = [], presentation: _presentation, ...originFirst } = baseline;
const preserved = [originFirst, ...next];
for (const entry of preserved) {
  for (const name of [entry.poster, entry.beats, ...entry.renditions.map(item => item.src)].filter(Boolean)) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) throw new Error('Unsafe baseline filename');
    const original = path.join(root, 'exports/lia-motion', name);
    const bytes = await readFile(original);
    await copyFile(original, path.join(destination, name));
    const copied = await readFile(path.join(destination, name));
    if (digest(bytes) !== digest(copied)) throw new Error(`Preservation failed: ${name}`);
    records.push({ file: name, bytes: bytes.length, sha256: digest(bytes), preserved: true });
  }
}
const manifest = { version: 1, ...first, next: preserved, presentation: first };
await writeFile(path.join(destination, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
await writeFile(path.join(delivery, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
await writeFile(path.join(delivery, 'delivery.json'), JSON.stringify({ baseUrl: previewBase, durationSeconds: 80, totalVideos: 1 + preserved.length, preservedEntries: preserved, records }, null, 2) + '\n');
await writeFile(path.join(delivery, 'dev-media.override.yml'), `services:\n  web:\n    environment:\n      LANDING_MEDIA_BASE_URL: ${JSON.stringify(previewBase)}\n`);
console.log(`DEV media packaged: 80s, ${1 + preserved.length} videos, ${records.length} verified files. Production configuration unchanged.`);
