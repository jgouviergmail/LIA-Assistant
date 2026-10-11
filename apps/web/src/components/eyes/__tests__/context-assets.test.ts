import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { webpEnvelope } from '@/components/spirit/__tests__/webp-envelope';

const CONTEXT_PROPS = [
  { name: 'rain', width: 128, height: 128 },
  { name: 'storm', width: 96, height: 96 },
  { name: 'cold', width: 192, height: 96 },
  { name: 'freezing', width: 128, height: 128 },
  { name: 'snow', width: 64, height: 64 },
  { name: 'hot', width: 96, height: 96 },
  { name: 'heat', width: 64, height: 64 },
  { name: 'fog', width: 128, height: 128 },
  { name: 'wind', width: 96, height: 96 },
  { name: 'night', width: 96, height: 96 },
] as const;

interface ContextAssetRecord {
  width: number;
  height: number;
  bytes: number;
  sha256: string;
}
interface ContextManifest {
  assets: Record<string, ContextAssetRecord>;
  total_bytes: number;
}

const directory = join(process.cwd(), 'public/avatars/context/v1');
const manifestBytes = readFileSync(join(directory, 'manifest.json'));
const manifest: ContextManifest = JSON.parse(manifestBytes.toString('utf8'));

describe('offline context prop delivery', () => {
  it.each(CONTEXT_PROPS)(
    '$name is an alpha still of the expected size matching its manifest',
    prop => {
      const bytes = readFileSync(join(directory, `${prop.name}.webp`));
      expect(webpEnvelope(bytes)).toMatchObject({
        width: prop.width,
        height: prop.height,
        alpha: true,
        animation: false,
        frames: 0,
      });
      expect(bytes.length).toBeLessThanOrEqual(16 * 1024);
      expect(manifest.assets[prop.name]).toEqual({
        width: prop.width,
        height: prop.height,
        bytes: bytes.length,
        sha256: createHash('sha256').update(bytes).digest('hex'),
      });
    }
  );

  it('ships only the ten props and a consistent manifest within the whole pack budget', () => {
    const names = CONTEXT_PROPS.map(prop => prop.name).sort();
    expect(Object.keys(manifest.assets).sort()).toEqual(names);
    expect(readdirSync(directory).sort()).toEqual(
      ['manifest.json', ...names.map(name => `${name}.webp`)].sort()
    );
    const totalBytes = names.reduce((total, name) => total + manifest.assets[name].bytes, 0);
    expect(manifest.total_bytes).toBe(totalBytes);
    expect(totalBytes + manifestBytes.length).toBeLessThanOrEqual(96 * 1024);
  });
});
