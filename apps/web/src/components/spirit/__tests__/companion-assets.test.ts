import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { companionBodyAsset, COMPANION_CHARACTERS } from '../companion-catalogue';
import { webpEnvelope } from './webp-envelope';

interface BodyRecord {
  size: number;
  bytes: number;
  sha256: string;
}

interface CompanionManifest {
  total_bytes: number;
  assets: Record<string, BodyRecord>;
}

describe.each(COMPANION_CHARACTERS)('Original %s companion delivery', character => {
  const directory = dirname(
    dirname(join(process.cwd(), 'public', companionBodyAsset(character, 'female')))
  );
  const manifest: CompanionManifest = JSON.parse(
    readFileSync(join(directory, 'manifest.json'), 'utf8')
  );

  it.each(['female', 'male'] as const)(
    '%s resolves to a complete, transparent, bounded still matching the recorded hash',
    variant => {
      const asset = companionBodyAsset(character, variant);
      const bytes = readFileSync(join(process.cwd(), 'public', asset));
      const recorded = manifest.assets[`${variant}/body`];
      expect(webpEnvelope(bytes)).toMatchObject({
        width: 192,
        height: 192,
        alpha: true,
        animation: false,
        frames: 0,
      });
      expect(bytes.length).toBeLessThanOrEqual(32 * 1024);
      expect(recorded.size).toBe(192);
      expect(recorded.bytes).toBe(bytes.length);
      expect(recorded.sha256).toBe(createHash('sha256').update(bytes).digest('hex'));
    }
  );

  it('ships both distinct genders without any unused animation or intermediate rendering file', () => {
    expect(readdirSync(directory).sort()).toEqual(['female', 'male', 'manifest.json']);
    const assets = ['female/body', 'male/body'];
    expect(Object.keys(manifest.assets).sort()).toEqual(assets);
    for (const variant of ['female', 'male']) {
      expect(readdirSync(join(directory, variant))).toEqual(['body.webp']);
    }
    const totalBytes = assets.reduce((total, name) => total + manifest.assets[name].bytes, 0);
    expect(manifest.total_bytes).toBe(totalBytes);
    expect(totalBytes + readFileSync(join(directory, 'manifest.json')).length).toBeLessThanOrEqual(
      80 * 1024
    );
    expect(manifest.assets['female/body'].sha256).not.toBe(manifest.assets['male/body'].sha256);
  });
});
