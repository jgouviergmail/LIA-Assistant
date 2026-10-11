import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { webpEnvelope } from '@/components/spirit/__tests__/webp-envelope';

interface ScarfAssetRecord {
  width: number;
  height: number;
  bytes: number;
  sha256: string;
  alpha: boolean;
}
interface ScarfManifest {
  total_bytes: number;
  assets: Record<string, ScarfAssetRecord>;
}
const directory = join(process.cwd(), 'public/avatars/scarf/v1');
const manifestBytes = readFileSync(join(directory, 'manifest.json'));
const manifest: ScarfManifest = JSON.parse(manifestBytes.toString('utf8'));

describe('offline scarf materials share a bounded still-only delivery', () => {
  it.each([
    { name: 'knit', size: 128, alpha: false },
    { name: 'front', size: 192, alpha: true },
  ])('$name matches its real dimensions, transparency and hash', ({ name, size, alpha }) => {
    const bytes = readFileSync(join(directory, `${name}.webp`));
    expect(webpEnvelope(bytes)).toMatchObject({
      width: size,
      height: size,
      alpha,
      animation: false,
      frames: 0,
    });
    expect(manifest.assets[name]).toEqual({
      width: size,
      height: size,
      bytes: bytes.length,
      alpha,
      sha256: createHash('sha256').update(bytes).digest('hex'),
    });
  });

  it('ships exactly the opaque knit, transparent fallback and coherent manifest within 32 KiB', () => {
    expect(readdirSync(directory).sort()).toEqual(['front.webp', 'knit.webp', 'manifest.json']);
    expect(Object.keys(manifest.assets).sort()).toEqual(['front', 'knit']);
    const total = manifest.assets.front.bytes + manifest.assets.knit.bytes;
    expect(manifest.total_bytes).toBe(total);
    expect(total + manifestBytes.length).toBeLessThanOrEqual(32 * 1024);
  });
});
