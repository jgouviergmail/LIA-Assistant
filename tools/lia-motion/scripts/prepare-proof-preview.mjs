import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { measuredLoudnessFilter, runFfmpeg } from './audio-master.mjs';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.resolve(project, '../../exports/lia-motion');
const name = process.argv[2] ?? 'proof30';
if (!['proof30', 'story24'].includes(name)) throw new Error('Unknown review composition');
const source = path.resolve(output, `${name}.mp4`);
const target = path.resolve(output, `${name}-preview.mp4`);
const normalized = measuredLoudnessFilter(['-i', source], '', -16);
runFfmpeg([
  '-i', source, '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy',
  '-af', normalized.filter, '-c:a', 'aac', '-b:a', '320k', '-ar', '48000',
  '-movflags', '+faststart', target,
]);
const encoded = measuredLoudnessFilter(['-i', target], '', -16).measurement;
if (Math.abs(Number(encoded.input_i) + 16) > 0.5 || Number(encoded.input_tp) > -0.8) {
  throw new Error(`Proof audio outside web target: ${JSON.stringify(encoded)}`);
}
const sha256 = async file => createHash('sha256').update(await readFile(file)).digest('hex');
await writeFile(path.resolve(output, `${name}-qualification.json`), JSON.stringify({
  scope: 'Web preview, not broadcaster acceptance or human listening review',
  sourceSha256: await sha256(source),
  sha256: await sha256(target),
  audioTargetLufs: -16,
  encodedAudio: encoded,
}, null, 2) + '\n');
console.log(target);
