/** Inspect the actual cached human artwork for all eight motion headings. */
import { test, expect } from '../fixtures';
import { installArtOracle } from '../fixtures/world-art';

test('world locomotion: eight distinct complete orientations and a reviewable gait sheet', async ({
  page,
}, info) => {
  await installArtOracle(page);
  const result = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1280;
    canvas.height = 610;
    document.body.append(canvas);
    const c = canvas.getContext('2d')!;
    c.fillStyle = '#eeeae1';
    c.fillRect(0, 0, 1280, 610);
    c.font = '16px sans-serif';
    c.fillStyle = '#294844';
    c.fillText('LIA World · actual motion headings and walking frames', 20, 28);
    const hashes: number[] = [],
      clipped: number[] = [];
    for (let heading = 0; heading < 8; heading++) {
      for (const [row, phase] of [0, 2, 6].entries()) {
        const sprite = window.worldArtOracle.paintActor(
          false,
          Math.floor(heading / 2),
          phase,
          1.5,
          'teal',
          heading
        );
        const ctx = sprite.canvas.getContext('2d')!,
          w = sprite.canvas.width,
          h = sprite.canvas.height;
        const pixels = ctx.getImageData(0, 0, w, h).data;
        let hash = 2166136261,
          opaque = 0;
        for (let i = 0; i < pixels.length; i++) hash = Math.imul(hash ^ pixels[i], 16777619) >>> 0;
        for (let y = 0; y < h; y++)
          for (let x = 0; x < w; x++)
            if (pixels[(y * w + x) * 4 + 3]) {
              opaque++;
              if (x === 0 || y === 0 || x === w - 1 || y === h - 1) clipped.push(heading);
            }
        if (!opaque) throw Error('Empty actor');
        if (row === 0) hashes.push(hash);
        c.drawImage(
          sprite.canvas,
          heading * 160 + 2,
          row * 180 + 45,
          156,
          (156 * sprite.height) / sprite.width
        );
        c.fillStyle = '#294844';
        c.fillText('heading ' + heading + ' / frame ' + phase, heading * 160 + 10, row * 180 + 65);
        sprite.canvas.width = 0;
      }
    }
    return { distinct: new Set(hashes).size, clipped };
  });
  expect(result.distinct).toBe(8);
  expect(result.clipped).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 630 });
  await page.screenshot({ path: info.outputPath('eight-directions.png') });
});
