#!/usr/bin/env node
/** Ten original offline props, aspect-preserving transparent padding, no runtime work.
 * Usage: node package_context_art.mjs inputs.json public/avatars/context/v1
 * Records: key, width, height, source and exact prompt.
 */
import { readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { encodeArtwork, isMain, publishImmutablePack } from './art-packaging.mjs';

export const CONTEXT_ART_SIZES = {
  rain: [128, 128],
  storm: [96, 96],
  cold: [192, 96],
  freezing: [128, 128],
  snow: [64, 64],
  hot: [96, 96],
  heat: [64, 64],
  fog: [128, 128],
  wind: [96, 96],
  night: [96, 96],
};

export async function publishContextArt(inputs, outputPath) {
  if (
    !Array.isArray(inputs) ||
    inputs.length !== 10 ||
    new Set(inputs.map(input => input?.key)).size !== 10
  )
    throw new Error('Context artwork requires all ten distinct keys without duplicates');
  for (const input of inputs) {
    const size = Object.hasOwn(CONTEXT_ART_SIZES, input.key)
      ? CONTEXT_ART_SIZES[input.key]
      : undefined;
    if (!size || input.width !== size[0] || input.height !== size[1])
      throw new Error(`Invalid contextual artwork dimensions: ${input.key}`);
  }
  return publishImmutablePack(outputPath, 96 * 1024, async stage => {
    const assets = {};
    const artwork = {};
    for (const input of inputs) {
      const encoded = await encodeArtwork(
        input,
        join(stage, `${input.key}.webp`),
        input.width,
        input.height,
        16 * 1024
      );
      assets[input.key] = encoded.record;
      artwork[input.key] = encoded.artwork;
    }
    return {
      version: 1,
      total_bytes: Object.values(assets).reduce((sum, asset) => sum + asset.bytes, 0),
      source:
        'Original contextual art directed with image generation; native rig supplies all motion',
      delivery: { codec: 'WebP', quality: 94, animation: false },
      artwork,
      assets,
    };
  });
}

if (isMain(import.meta.url)) {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) throw new Error('Expected inputs.json and output directory');
  const manifest = await publishContextArt(
    JSON.parse(await readFile(resolve(inputPath), 'utf8')),
    outputPath
  );
  process.stdout.write(`context/v1: ${manifest.total_bytes} bytes, ten transparent still props\n`);
}
