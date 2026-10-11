import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { SPIRIT_EXPRESSIONS } from '../catalogue';
import { webpEnvelope } from './webp-envelope';

const variants = ['female', 'male'] as const;
const organs = ['eye', 'eye-right', 'iris', 'sclera-mask', 'sclera-mask-right'] as const;
const assetRoot = join(process.cwd(), 'public', 'avatars', 'spirit', 'v1');
const portraits = variants.flatMap(variant =>
  SPIRIT_EXPRESSIONS.map(expression => `compact/${variant}/${expression}`)
);
const files = [
  ...portraits.flatMap(portrait => [`${portrait}.webp`, `${portrait}-still.webp`]),
  ...variants.map(variant => `${variant}/body.webp`),
  ...variants.flatMap(variant => organs.map(organ => `${variant}/${organ}.webp`)),
];
const readAsset = (path: string) => readFileSync(join(assetRoot, path));
const digest = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');

/** Asset generation is offline; missing, extra or oversized shipped assets fail CI. */
describe('Shipped Spirit portraits', () => {
  it.each(portraits)('%s supplies a transparent 96 px still and a bounded clip', portrait => {
    const still = readAsset(`${portrait}-still.webp`);
    const clip = readAsset(`${portrait}.webp`);
    expect(webpEnvelope(still)).toMatchObject({
      width: 96,
      height: 96,
      alpha: true,
      animation: false,
      frames: 0,
    });
    expect(webpEnvelope(clip)).toMatchObject({
      width: 96,
      height: 96,
      alpha: true,
      animation: true,
      durationMs: 3200,
    });
    expect(webpEnvelope(clip).frames).toBeGreaterThan(1);
    expect(clip.length).toBeLessThanOrEqual(80 * 1024);
  });

  it.each(variants)('%s supplies a small transparent 192 px fixed body', variant => {
    const body = readAsset(`${variant}/body.webp`);
    expect(webpEnvelope(body)).toMatchObject({
      width: 192,
      height: 192,
      alpha: true,
      animation: false,
      frames: 0,
    });
    expect(body.length).toBeLessThanOrEqual(32 * 1024);
  });

  it.each(variants.flatMap(variant => organs.map(organ => `${variant}/${organ}`)))(
    '%s supplies a small transparent 128 px fixed organ',
    path => {
      const organ = readAsset(`${path}.webp`);
      expect(webpEnvelope(organ)).toMatchObject({
        width: 128,
        height: 128,
        alpha: true,
        animation: false,
        frames: 0,
      });
      expect(organ.length).toBeLessThanOrEqual(32 * 1024);
    }
  );

  it('ships exactly 80 compact portraits, two bodies and ten organs including sclera masks', () => {
    const shipped = readdirSync(assetRoot, { recursive: true, encoding: 'utf8' })
      .filter(path => path.endsWith('.webp'))
      .map(path => path.replaceAll('\\', '/'));
    expect(shipped.sort()).toEqual([...files].sort());
  });

  it('keeps the complete pack within 3 MiB', () => {
    expect(files.reduce((sum, path) => sum + readAsset(path).length, 0)).toBeLessThanOrEqual(
      3 * 1024 * 1024
    );
  });

  it('publishes a manifest that exactly describes every shipped WebP', () => {
    const manifest = JSON.parse(readAsset('manifest.json').toString('utf8'));
    expect(Object.keys(manifest.portraits).sort()).toEqual([...portraits].sort());
    expect(Object.keys(manifest.bodies).sort()).toEqual([...variants].sort());
    expect(Object.keys(manifest.organs).sort()).toEqual([...variants].sort());
    for (const portrait of portraits) {
      const still = readAsset(`${portrait}-still.webp`);
      const clip = readAsset(`${portrait}.webp`);
      const envelope = webpEnvelope(clip);
      expect(manifest.portraits[portrait]).toEqual({
        size: envelope.width,
        frames: envelope.frames,
        duration_ms: envelope.durationMs,
        clip_bytes: clip.length,
        still_bytes: still.length,
        sha256: digest(clip),
        still_sha256: digest(still),
      });
    }
    for (const variant of variants) {
      const body = readAsset(`${variant}/body.webp`);
      expect(manifest.bodies[variant]).toEqual({
        size: webpEnvelope(body).width,
        bytes: body.length,
        sha256: digest(body),
      });
      expect(Object.keys(manifest.organs[variant]).sort()).toEqual([...organs].sort());
      for (const organ of organs) {
        const bytes = readAsset(`${variant}/${organ}.webp`);
        expect(manifest.organs[variant][organ]).toEqual({
          size: webpEnvelope(bytes).width,
          bytes: bytes.length,
          sha256: digest(bytes),
        });
      }
    }
    expect(manifest.total_bytes).toBe(files.reduce((sum, path) => sum + readAsset(path).length, 0));
  });
});
