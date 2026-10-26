/**
 * Offline lossless repack of LIA's authored poses. Run from the repository root:
 * node scripts/pack-world-lia-atlas.cjs
 * Sharp is already supplied by Next.js; it is not a new runtime dependency.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const sharp = require(
  require.resolve('sharp', {
    paths: [
      path.dirname(require.resolve(path.join(root, 'apps/web/node_modules/next/package.json'))),
    ],
  })
);
const sourcePath = 'tools/world-art/source/bip-v1/directions.png';
const targetDir = path.join(root, 'apps/web/public/world/bip/v2');
const sourceFrames = [
  { x: 141, y: 101, width: 380, height: 467 },
  { x: 736, y: 100, width: 396, height: 471 },
  { x: 149, y: 696, width: 388, height: 470 },
  { x: 719, y: 695, width: 386, height: 472 },
];
const gutter = 2;
const width = 800,
  height = 952;
const sha256 = data => crypto.createHash('sha256').update(data).digest('hex');
async function main() {
  const source = fs.readFileSync(path.join(root, sourcePath));
  const decoded = await sharp(source).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  if (decoded.info.width !== 1254 || decoded.info.height !== 1254 || decoded.info.channels !== 4) {
    throw new Error('Authored source dimensions changed: review the frame bounds before repacking');
  }
  const output = Buffer.alloc(width * height * 4);
  const frames = sourceFrames.map((frame, i) => {
    const dest = { ...frame, x: gutter + (i % 2) * 400, y: gutter + Math.floor(i / 2) * 476 };
    // Copy RGBA directly, including source gutters; compositing would change translucent pixels.
    for (let y = -gutter; y < frame.height + gutter; y++) {
      const offset = ((frame.y + y) * decoded.info.width + frame.x - gutter) * 4;
      const count = (frame.width + gutter * 2) * 4;
      decoded.data.copy(
        output,
        ((dest.y + y) * width + dest.x - gutter) * 4,
        offset,
        offset + count
      );
    }
    return dest;
  });
  const png = await sharp(output, { raw: { width, height, channels: 4 } })
    .png({ compressionLevel: 9, palette: false, adaptiveFiltering: true })
    .toBuffer();
  const check = await sharp(png).ensureAlpha().raw().toBuffer();
  for (let i = 0; i < frames.length; i++) {
    const src = sourceFrames[i],
      dst = frames[i];
    for (let y = -gutter; y < src.height + gutter; y++) {
      const count = (src.width + gutter * 2) * 4;
      const a = ((src.y + y) * decoded.info.width + src.x - gutter) * 4;
      const b = ((dst.y + y) * width + dst.x - gutter) * 4;
      if (!decoded.data.subarray(a, a + count).equals(check.subarray(b, b + count))) {
        throw new Error('Repacked pose differs from authored RGBA pixels');
      }
    }
  }
  fs.mkdirSync(targetDir, { recursive: true });
  fs.writeFileSync(path.join(targetDir, 'directions.png'), png);
  const json = (name, data) =>
    fs.writeFileSync(path.join(targetDir, name), JSON.stringify(data, null, 2) + '\n');
  json('layout.json', { src: '/world/bip/v2/directions.png', width, height, frames });
  json('provenance.json', {
    operation: 'lossless RGBA repack with source-pixel gutters; no resampling or generated art',
    source: sourcePath,
    sourceSha256: sha256(source),
    outputSha256: sha256(png),
    sourceFrames,
    gutter,
    originalRetained: true,
    decodedBytesBefore: decoded.data.length,
    decodedBytesAfter: check.length,
    note: 'Original content credentials remain with the offline source under tools/world-art. They do not attest this derivative.',
  });
  process.stdout.write(
    JSON.stringify({
      bytesBefore: source.length,
      bytesAfter: png.length,
      decodedBefore: decoded.data.length,
      decodedAfter: check.length,
      exactRGBA: true,
    }) + '\n'
  );
}
main().catch(error => {
  process.stderr.write(String(error) + '\n');
  process.exitCode = 1;
});
