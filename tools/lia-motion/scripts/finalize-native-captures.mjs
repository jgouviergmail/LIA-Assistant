/** Trim native UI filming to reviewable application interactions, without replacing any pixels. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const manifestPath = path.join(project, 'public/capture-v2/manifest.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const selected = process.argv.slice(2);
const converted = [];
for (const asset of manifest.assets) {
  if (!asset.clipRawPath || (selected.length && !selected.includes(asset.id))) continue;
  const source = path.join(project, 'public', asset.clipRawPath);
  const destination = path.join(project, 'public/capture-v2/fr', `${asset.id}.mp4`);
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-ss', String(asset.clipStartSeconds), '-i', source, '-t', String(asset.durationSeconds), '-an', '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-movflags', '+faststart', destination], { timeout: 60000, stdio: 'pipe' });
  const probe = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', destination], { encoding: 'utf8', timeout: 10000 }));
  const video = probe.streams.find(stream => stream.codec_type === 'video');
  if (video.width !== asset.width || video.height !== asset.height || video.r_frame_rate !== '30/1') throw new Error(`Unexpected native clip dimensions/rate ${asset.id}`);
  asset.clipPath = `capture-v2/fr/${asset.id}.mp4`;
  asset.fromSeconds = 0;
  asset.durationSeconds = Number(probe.format.duration);
  asset.clipSha256 = crypto.createHash('sha256').update(fs.readFileSync(destination)).digest('hex');
  asset.codec = 'h264';
  asset.fps = 30;
  converted.push({ id: asset.id, durationSeconds: asset.durationSeconds, path: asset.clipPath });
}
const chat = manifest.assets.find(asset => asset.id === 'chat' && asset.clipPath);
if (chat) manifest.assets = manifest.assets.filter(asset => asset.id !== 'dossier').concat({ ...chat, id: 'dossier', aliases: ['chat'], semanticScope: 'native chat cross-source dossier demo and follow-up question, no inference performed' });
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify(converted));
