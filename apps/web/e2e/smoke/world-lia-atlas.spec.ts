import { test, expect } from '../fixtures';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import layout from '../../public/world/bip/v2/layout.json';
import provenance from '../../public/world/bip/v2/provenance.json';

test('lossless LIA packing preserves all directional pixels at fractional zooms', async ({
  page,
}, info) => {
  const publicRoot = resolve(__dirname, '../../public');
  // The unrepacked authoring input is deliberately outside the served assets.
  const original = readFileSync(resolve(__dirname, '../../../..', provenance.source));
  expect(createHash('sha256').update(original).digest('hex')).toBe(provenance.sourceSha256);
  await page.route('**/world/bip/*/directions.png', route => {
    const version = new URL(route.request().url()).pathname.includes('/v2/') ? 'v2' : 'v1';
    return route.fulfill({
      contentType: 'image/png',
      body:
        version === 'v1'
          ? original
          : readFileSync(resolve(publicRoot, 'world/bip', version, 'directions.png')),
    });
  });
  await page.route('**/world-atlas-oracle', route =>
    route.fulfill({
      contentType: 'text/html',
      headers: { 'Content-Security-Policy': "default-src 'none'; img-src 'self'" },
      body: '<!doctype html><html lang="en"><title>LIA pixel comparison</title><body></body></html>',
    })
  );
  await page.goto('/world-atlas-oracle');
  const result = await page.evaluate(
    async ({ layout, sourceFrames }) => {
      const load = (src: string) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve(image);
          image.onerror = reject;
          image.src = src;
        });
      const old = await load('/world/bip/v1/directions.png'),
        packed = await load(layout.src);
      const surface = () => {
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 256;
        const c = canvas.getContext('2d', { willReadFrequently: true });
        if (!c) throw Error('No canvas');
        return { canvas, c };
      };
      const before = surface(),
        after = surface();
      let different = 0,
        nonzero = 0,
        cases = 0;
      for (let i = 0; i < sourceFrames.length; i++)
        for (const size of [35, 70, 105, 143.2])
          for (const smoothing of [false, true]) {
            for (const [target, image, frame] of [
              [before, old, sourceFrames[i]],
              [after, packed, layout.frames[i]],
            ] as const) {
              target.c.clearRect(0, 0, 256, 256);
              target.c.imageSmoothingEnabled = smoothing;
              target.c.drawImage(
                image,
                frame.x,
                frame.y,
                frame.width,
                frame.height,
                71.25,
                53.75,
                (frame.width * size) / frame.height,
                size
              );
            }
            const a = before.c.getImageData(0, 0, 256, 256).data;
            const b = after.c.getImageData(0, 0, 256, 256).data;
            for (let j = 0; j < a.length; j++) {
              if (a[j] !== b[j]) different++;
              if (a[j]) nonzero++;
            }
            cases++;
          }
      before.canvas.width = after.canvas.width = 0;
      return {
        different,
        nonzero,
        cases,
        width: packed.naturalWidth,
        height: packed.naturalHeight,
      };
    },
    { layout, sourceFrames: provenance.sourceFrames }
  );
  expect(result).toMatchObject({
    different: 0,
    cases: 32,
    width: layout.width,
    height: layout.height,
  });
  expect(result.nonzero).toBeGreaterThan(10000);
  expect(result.width * result.height * 4).toBeLessThan(3_100_000);
  await info.attach('LIA-pixel-equivalence', {
    body: JSON.stringify(result),
    contentType: 'application/json',
  });
});
