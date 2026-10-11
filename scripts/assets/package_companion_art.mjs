#!/usr/bin/env node
/** Package reviewed original artwork; immutable versions contain a complete pair.
 * FFmpeg is offline only. Usage: node package_companion_art.mjs inputs.json public/avatars
 * Records: character, variant, version, source, prompt. No painting or runtime dependency.
 */
import { mkdir, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { encodeArtwork, isMain, publishImmutablePack } from './art-packaging.mjs';

function validateInput(input) {
  if (!input || !/^[a-z][a-z0-9-]*$/.test(input.character))
    throw new Error('Invalid character identity');
  if (!['male', 'female'].includes(input.variant)) throw new Error('Invalid variant');
  if (!Number.isInteger(input.version) || input.version < 1) throw new Error('Invalid version');
}

export async function publishCompanionArt(inputs, outputPath) {
  if (!Array.isArray(inputs) || !inputs.length)
    throw new Error('Artwork input must be a nonempty record array');
  inputs.forEach(validateInput);
  const groups = Map.groupBy(inputs, input => `${input.character}/v${input.version}`);
  for (const [identity, group] of groups) {
    if (group.length !== 2 || new Set(group.map(input => input.variant)).size !== 2)
      throw new Error(`Each character requires one reviewed body per gender: ${identity}`);
  }
  const delivered = [];
  for (const [identity, group] of groups) {
    const manifest = await publishImmutablePack(
      join(resolve(outputPath), identity),
      80 * 1024,
      async stage => {
        const assets = {};
        const artwork = {};
        for (const input of group) {
          await mkdir(join(stage, input.variant));
          const encoded = await encodeArtwork(
            input,
            join(stage, input.variant, 'body.webp'),
            192,
            192,
            32 * 1024
          );
          const { width: _width, height: _height, ...record } = encoded.record;
          assets[`${input.variant}/body`] = { size: 192, ...record };
          artwork[input.variant] = encoded.artwork;
        }
        return {
          version: group[0].version,
          character: group[0].character,
          total_bytes: Object.values(assets).reduce((sum, asset) => sum + asset.bytes, 0),
          source:
            'Original art directed with image generation; native rig supplies the complete live face',
          delivery: { size: 192, codec: 'WebP', quality: 94, animation: false },
          artwork,
          assets,
        };
      }
    );
    delivered.push({ identity, total_bytes: manifest.total_bytes });
  }
  return delivered;
}

if (isMain(import.meta.url)) {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) throw new Error('Expected inputs.json and output directory');
  for (const pack of await publishCompanionArt(
    JSON.parse(await readFile(resolve(inputPath), 'utf8')),
    outputPath
  ))
    process.stdout.write(`${pack.identity}: ${pack.total_bytes} bytes, two 192px bodies\n`);
}
