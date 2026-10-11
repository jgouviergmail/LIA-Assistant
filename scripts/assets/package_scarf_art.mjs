#!/usr/bin/env node
/** Offline scarf material plus front-only fallback; native volume owns its drape. */
import { readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { encodeArtwork, publishImmutablePack } from './art-packaging.mjs';

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath)
  throw new Error('Expected reviewed scarf inputs and version directory');
const inputs = JSON.parse(await readFile(resolve(inputPath), 'utf8'));
if (
  !Array.isArray(inputs) ||
  inputs.length !== 2 ||
  new Set(inputs.map(input => input.key)).size !== 2 ||
  !inputs.every(input => ['knit', 'front'].includes(input.key))
) {
  throw new Error('Scarf requires exactly one knit material and one front-only fallback');
}
const manifest = await publishImmutablePack(resolve(outputPath), 32 * 1024, async stage => {
  const assets = {};
  const artwork = {};
  for (const input of inputs) {
    const size = input.key === 'knit' ? 128 : 192;
    const result = await encodeArtwork(
      input,
      join(stage, `${input.key}.webp`),
      size,
      size,
      16 * 1024,
      input.key === 'front'
    );
    assets[input.key] = { ...result.record, alpha: input.key === 'front' };
    artwork[input.key] = result.artwork;
  }
  return {
    version: 1,
    total_bytes: Object.values(assets).reduce((sum, asset) => sum + asset.bytes, 0),
    source:
      'Original knit material and front-only scarf; native geometry supplies the collar and occlusion',
    artwork,
    assets,
    delivery: { codec: 'WebP', quality: 94, animation: false },
  };
});
process.stdout.write(`scarf/v1: ${manifest.total_bytes} bytes\n`);
