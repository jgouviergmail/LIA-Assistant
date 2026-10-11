import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import manifest from '../../../../public/avatars/smiley/v1/manifest.json';
import { webpEnvelope } from '@/components/spirit/__tests__/webp-envelope';

const directory = join(process.cwd(), 'public/avatars/smiley/v1');
const layers = { body: 192, eye: 128, iris: 128, 'sclera-mask': 128, bow: 128 } as const;

describe('Original golden Smiley asset', () => {
  it.each(Object.entries(layers))(
    '%s is a bounded transparent still with its recorded hash',
    (name, size) => {
      const bytes = readFileSync(join(directory, `${name}.webp`));
      const recorded = manifest.assets[name as keyof typeof layers];
      expect(webpEnvelope(bytes)).toMatchObject({
        width: size,
        height: size,
        alpha: true,
        animation: false,
        frames: 0,
      });
      expect(bytes.length).toBeLessThanOrEqual(32 * 1024);
      expect(recorded.size).toBe(size);
      expect(recorded.bytes).toBe(bytes.length);
      expect(recorded.sha256).toBe(createHash('sha256').update(bytes).digest('hex'));
    }
  );

  it('ships only the fixed layers and manifest within the complete delivery budget', () => {
    expect(Object.keys(manifest.assets).sort()).toEqual(Object.keys(layers).sort());
    expect(readdirSync(directory).sort()).toEqual([
      'body.webp',
      'bow.webp',
      'eye.webp',
      'iris.webp',
      'manifest.json',
      'sclera-mask.webp',
    ]);
    const textureBytes = Object.keys(layers).reduce(
      (sum, name) => sum + readFileSync(join(directory, `${name}.webp`)).length,
      0
    );
    expect(manifest.total_bytes).toBe(textureBytes);
    expect(
      textureBytes + readFileSync(join(directory, 'manifest.json')).length
    ).toBeLessThanOrEqual(128 * 1024);
  });
});
