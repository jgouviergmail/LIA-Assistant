import { readFileSync, existsSync } from 'node:fs';
import { resolve, basename } from 'node:path';
import { createHash } from 'node:crypto';
import { expect, it } from 'vitest';
import { SOUND_FILES, soundUrl, ambientFor, type SoundId } from '../audio/catalogue';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
it('ships every declared sound with matching provenance, output integrity and a cache revision', () => {
  const root = resolve(process.cwd(), 'public/world/audio/v1');
  const manifest: {
    asset_revision: number;
    assets: { id: string; file: string; sha256: string }[];
  } = JSON.parse(readFileSync(resolve(root, 'provenance.json'), 'utf8'));
  for (const id of Object.keys(SOUND_FILES) as SoundId[]) {
    const url = new URL(soundUrl(id), 'https://sound.test');
    expect(url.searchParams.get('v')).toBe(String(manifest.asset_revision));
    const path = resolve(root, basename(url.pathname));
    expect(existsSync(path), id).toBe(true);
    const provenance = manifest.assets.find(a => a.id === id);
    expect(provenance?.file).toBe(basename(path));
    expect(createHash('sha256').update(readFileSync(path)).digest('hex')).toBe(provenance?.sha256);
  }
  expect(ambientFor('undeclared-room', NEUTRAL_ATMOSPHERE)).toBeNull();
});
